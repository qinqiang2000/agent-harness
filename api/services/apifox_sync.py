"""Apifox API documentation sync service.

Fetches API endpoints from Apifox and writes them as Markdown files
into agent_cwd/data/kb/接口文档/ for use by issue-diagnosis skill.
"""

import asyncio
import json
import logging
import os
import re
from datetime import datetime
from pathlib import Path

import httpx

from api.constants import DATA_DIR

logger = logging.getLogger(__name__)

KB_API_DOC_DIR = DATA_DIR / "kb" / "接口文档"

APIFOX_BASE_URL = "https://api.apifox.com/api/v1"
APIFOX_PUB_BASE_URL = "https://api.apifox.com/api/v1/published-projects"


class ApifoxSyncService:
    """Syncs API documentation from Apifox to local KB Markdown files."""

    def __init__(self, token: str, project_id: str, online_id: str | None = None):
        self.token = token
        self.project_id = project_id
        # online_id 用于 published-projects API（doc 同步），默认与 project_id 相同
        self.online_id = online_id or project_id
        self._lock = asyncio.Lock()
        self._schema_map: dict[str, dict] = {}  # schema_id -> jsonSchema

    def _resolve_refs(self, schema: dict, visited: frozenset[str] = frozenset()) -> dict:
        """递归将 $ref (#/definitions/{id}) 替换为实际 schema 内容，防止循环引用。"""
        if not isinstance(schema, dict):
            return schema

        ref = schema.get("$ref")
        if ref and isinstance(ref, str):
            # 格式: #/definitions/{id}
            schema_id = ref.split("/")[-1]
            if schema_id in visited:
                return {"type": "object", "description": f"[循环引用: {schema_id}]"}
            resolved = self._schema_map.get(schema_id)
            if resolved:
                return self._resolve_refs(resolved, visited | {schema_id})
            return schema

        return {
            k: self._resolve_refs_value(v, visited)
            for k, v in schema.items()
        }

    def _resolve_refs_value(self, value: object, visited: frozenset[str]) -> object:
        if isinstance(value, dict):
            return self._resolve_refs(value, visited)
        if isinstance(value, list):
            return [self._resolve_refs_value(item, visited) for item in value]
        return value

    def _build_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "X-Apifox-Api-Version": "2024-03-28",
            "Content-Type": "application/json",
        }

    def _sanitize_filename(self, name: str) -> str:
        """Replace characters unsafe for filenames."""
        return re.sub(r'[\s/\\:*?"<>|]', "_", name)

    def _format_props(self, props: dict, required_fields: list, indent: int = 2) -> list[str]:
        """递归格式化 JSON Schema properties 为 Markdown 列表。"""
        lines = []
        prefix = "  " * indent
        for fname, fdef in props.items():
            ftype = fdef.get("type", "")
            fdesc = (fdef.get("description") or "").split("\n")[0][:150]
            req_mark = "必填" if fname in required_fields else "可选"
            line = f"{prefix}- `{fname}` ({ftype}, {req_mark}){': ' + fdesc if fdesc else ''}"
            lines.append(line)
            # 展开嵌套 object
            sub_props = fdef.get("properties") or {}
            if sub_props:
                sub_required = fdef.get("required") or []
                lines.extend(self._format_props(sub_props, sub_required, indent + 1))
            # 展开 array items
            items = fdef.get("items") or {}
            item_props = items.get("properties") or {}
            if item_props:
                item_required = items.get("required") or []
                lines.append(f"{prefix}  (数组元素字段:)")
                lines.extend(self._format_props(item_props, item_required, indent + 2))
        return lines

    def _format_endpoint(self, endpoint: dict) -> str:
        """Format a single endpoint dict as a Markdown section."""
        name = endpoint.get("name", "未命名接口")
        method = (endpoint.get("method") or "").upper()
        path = endpoint.get("path", "")
        description = endpoint.get("description") or ""
        status = endpoint.get("status", "")

        lines = [
            f"### {name}",
            "",
            f"- **方法**: `{method}`",
            f"- **路径**: `{path}`",
        ]
        if status:
            lines.append(f"- **状态**: {status}")
        # 完整输出描述（不截断）
        if description:
            lines.append("")
            lines.append("**描述**:")
            lines.append("")
            lines.append(description.strip())
            lines.append("")

        # Query / Path 参数
        params = endpoint.get("parameters") or {}
        query_params = params.get("query", []) if isinstance(params, dict) else []
        path_params = params.get("path", []) if isinstance(params, dict) else []
        all_params = path_params + query_params
        if all_params:
            lines.append("**参数**:")
            for p in all_params:
                required = "必填" if p.get("required") else "可选"
                pname = p.get("name", "")
                ptype = p.get("type", "string")
                pdesc = (p.get("description") or "").split("\n")[0][:150]
                lines.append(f"  - `{pname}` ({ptype}, {required}){': ' + pdesc if pdesc else ''}")
            lines.append("")

        # 请求体（递归展开嵌套字段）
        req_body = endpoint.get("requestBody") or {}
        if req_body:
            content_type = req_body.get("type", "")
            schema = req_body.get("jsonSchema") or {}
            props = schema.get("properties") or {}
            if props:
                lines.append(f"**请求体** ({content_type}):")
                required_fields = schema.get("required") or []
                lines.extend(self._format_props(props, required_fields, indent=1))
                lines.append("")

        # 响应
        responses = endpoint.get("responses") or []
        if responses:
            lines.append("**响应**:")
            for resp in responses:
                code = resp.get("code", "")
                resp_name = resp.get("name", "")
                desc = (resp.get("description") or "").strip()
                schema = resp.get("jsonSchema") or {}
                props = schema.get("properties") or {}
                lines.append(f"  - `{code}` {resp_name}{': ' + desc if desc else ''}")
                if props:
                    required_fields = schema.get("required") or []
                    lines.extend(self._format_props(props, required_fields, indent=2))
            lines.append("")

        lines.append("")
        return "\n".join(lines)

    def _write_group_file(self, folder_name: str, endpoints: list[dict], target_dir: Path) -> Path:
        """Write a folder's endpoints to a Markdown file inside target_dir."""
        target_dir.mkdir(parents=True, exist_ok=True)
        safe_name = self._sanitize_filename(folder_name)
        file_path = target_dir / f"{safe_name}.md"

        assert len(endpoints) == 1, "每个接口单独一个文件，endpoints 应只有一条"
        ep = endpoints[0]

        lines = [
            f"# {folder_name}",
            "",
            f"> 自动同步自 Apifox，最后更新：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            f"**方法**: `{(ep.get('method') or '').upper()}`  ",
            f"**路径**: `{ep.get('path', '')}`  ",
            f"**状态**: {ep.get('status', '')}",
            "",
        ]

        # 完整原始数据（JSON），供 Agent 直接读取
        raw = {k: ep[k] for k in [
            "description", "parameters", "requestBody", "responses"
        ] if ep.get(k)}
        if raw:
            lines.append("```json")
            lines.append(json.dumps(raw, ensure_ascii=False, indent=2))
            lines.append("```")

        file_path.write_text("\n".join(lines), encoding="utf-8")
        # logger.info("Written endpoint to %s", file_path)
        return file_path

    def _collect_doc_nodes(self, nodes: list[dict], path_parts: list[str] | None = None) -> list[dict]:
        """递归从 http-api-tree 里收集所有 type=doc 节点，返回 [{id, name, path_parts}]。"""
        if path_parts is None:
            path_parts = []
        results = []
        for node in nodes:
            name = node.get("name", "")
            node_type = node.get("type", "")
            cur_parts = path_parts + [name]
            if node_type == "doc":
                doc = node.get("doc") or {}
                doc_id = doc.get("id")
                if doc_id:
                    results.append({"id": doc_id, "name": name, "path_parts": cur_parts})
            # 非 doc 节点才递归子节点（doc 节点没有子节点）
            if node_type != "doc":
                results.extend(self._collect_doc_nodes(node.get("children") or [], cur_parts))
        return results

    def _write_doc_file(self, doc_name: str, content: str, target_dir: Path) -> Path:
        """将 doc markdown 内容写入文件。"""
        target_dir.mkdir(parents=True, exist_ok=True)
        safe_name = self._sanitize_filename(doc_name)
        file_path = target_dir / f"{safe_name}.md"
        header = (
            f"# {doc_name}\n\n"
            f"> 自动同步自 Apifox，最后更新：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        )
        file_path.write_text(header + content, encoding="utf-8")
        logger.info("Written doc to %s", file_path)
        return file_path

    def _doc_api_base(self) -> str:
        """根据 online_id 格式判断使用 shared-docs 还是 published-projects。"""
        # UUID 格式（含连字符）用 shared-docs，纯数字 ID 用 published-projects
        if "-" in self.online_id:
            return f"{APIFOX_BASE_URL}/shared-docs/{self.online_id}"
        return f"{APIFOX_PUB_BASE_URL}/{self.online_id}"

    async def _sync_docs_inner(self, base_dir: Path) -> dict:
        """内部实现：同步 doc 类型文档，调用方负责持有锁。"""
        doc_api_base = self._doc_api_base()
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                headers = self._build_headers()
                tree_resp = await client.get(
                    f"{doc_api_base}/http-api-tree",
                    headers=headers,
                )
                tree_resp.raise_for_status()
                tree_data = tree_resp.json()
        except httpx.TimeoutException:
            logger.error("Apifox doc-tree request timed out for project %s", self.project_id)
            return {"docs": 0}
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                logger.info("No published doc site for project %s (online_id=%s), skipping doc sync", self.project_id, self.online_id)
            else:
                logger.error("Apifox HTTP error %s for project %s doc-tree", exc.response.status_code, self.project_id)
            return {"docs": 0}

        doc_nodes = self._collect_doc_nodes(tree_data.get("data") or [])
        if not doc_nodes:
            logger.info("No doc nodes found for project %s", self.project_id)
            return {"docs": 0}

        sem = asyncio.Semaphore(10)

        async def fetch_doc(client: httpx.AsyncClient, node: dict) -> tuple[dict, str]:
            async with sem:
                try:
                    r = await client.get(
                        f"{doc_api_base}/doc/{node['id']}",
                        headers=self._build_headers(),
                    )
                    r.raise_for_status()
                    content = r.json().get("data", {}).get("content") or ""
                    return node, content
                except Exception:
                    logger.warning("Failed to fetch doc %s (%s)", node["id"], node["name"])
                    return node, ""

        async with httpx.AsyncClient(timeout=30, limits=httpx.Limits(max_connections=10)) as doc_client:
            tasks = [fetch_doc(doc_client, node) for node in doc_nodes]
            results = await asyncio.gather(*tasks)

        synced_files = []
        for node, content in results:
            if not content:
                continue
            parts = node["path_parts"]
            if len(parts) > 1:
                safe_parts = [self._sanitize_filename(p) for p in parts[:-1]]
                target_dir = base_dir / Path(*safe_parts)
            else:
                target_dir = base_dir
            file_path = self._write_doc_file(node["name"], content, target_dir)
            synced_files.append(str(file_path.relative_to(base_dir)))

        logger.info("Apifox doc sync complete: %d docs for project %s", len(synced_files), self.project_id)
        return {"docs": len(synced_files)}

    async def sync_docs(self, project_name: str = "") -> dict:
        """独立同步 doc 类型文档（可单独调用）。"""
        base_dir = KB_API_DOC_DIR / project_name if project_name else KB_API_DOC_DIR
        async with self._lock:
            return await self._sync_docs_inner(base_dir)

    def _update_sync_meta(self, synced_files: list[str], base_dir: Path) -> None:
        base_dir.mkdir(parents=True, exist_ok=True)
        sync_meta_file = base_dir / "_sync_meta.json"
        meta = {
            "last_sync": datetime.now().isoformat(),
            "files": synced_files,
        }
        sync_meta_file.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    def _get_folder_path(self, folder_id: int, folder_by_id: dict[int, dict], _visited: frozenset[int] = frozenset()) -> list[str]:
        """返回从根到该文件夹的名称列表，用于构建目录路径。防止循环引用。"""
        if folder_id in _visited or folder_id not in folder_by_id:
            return []
        folder = folder_by_id[folder_id]
        parent_id = folder.get("parentId", 0)
        parent_path = self._get_folder_path(parent_id, folder_by_id, _visited | {folder_id})
        return parent_path + [folder["name"]]

    async def sync(self, project_name: str = "") -> dict:
        """
        Fetch all API folders and endpoints from Apifox, write to KB.
        Mirrors Apifox folder hierarchy as subdirectories.
        Returns summary dict with counts.
        """
        base_dir = KB_API_DOC_DIR / project_name if project_name else KB_API_DOC_DIR

        async with self._lock:
            try:
                async with httpx.AsyncClient(timeout=30) as client:
                    headers = self._build_headers()
                    folders_resp, apis_resp, schemas_resp = await asyncio.gather(
                        client.get(f"{APIFOX_BASE_URL}/projects/{self.project_id}/api-folders", headers=headers),
                        client.get(f"{APIFOX_BASE_URL}/projects/{self.project_id}/http-apis", headers=headers),
                        client.get(f"{APIFOX_BASE_URL}/projects/{self.project_id}/data-schemas", headers=headers),
                    )
                    folders_resp.raise_for_status()
                    apis_resp.raise_for_status()
                    folders_data = folders_resp.json()
                    apis_data = apis_resp.json()
                    # data-schemas 可能返回空，容错处理
                    schemas_data = schemas_resp.json() if schemas_resp.text else {"data": []}
            except httpx.TimeoutException:
                logger.error("Apifox request timed out for project %s", self.project_id)
                raise
            except httpx.HTTPStatusError as exc:
                logger.error("Apifox HTTP error %s for project %s", exc.response.status_code, self.project_id)
                raise

            # 构建 schema_id -> jsonSchema 映射，供 $ref 解析使用
            self._schema_map = {
                str(s["id"]): s.get("jsonSchema") or {}
                for s in schemas_data.get("data", [])
                if s.get("id")
            }

            # 构建 folderId -> folder 映射（排除 root）
            folder_by_id: dict[int, dict] = {
                f["id"]: f
                for f in folders_data.get("data", [])
                if f.get("type") != "root"
            }

            # 同步前清理整个项目目录，重建干净的目录树
            import shutil
            if base_dir.exists():
                shutil.rmtree(base_dir)
            base_dir.mkdir(parents=True, exist_ok=True)

            # 并发拉取所有接口详情（限制并发数避免限流）
            apis_list = apis_data.get("data", [])
            sem = asyncio.Semaphore(20)

            async def fetch_detail(client: httpx.AsyncClient, api_id: int) -> dict:
                async with sem:
                    try:
                        r = await client.get(
                            f"{APIFOX_BASE_URL}/projects/{self.project_id}/http-apis/{api_id}",
                            headers=self._build_headers(),
                        )
                        r.raise_for_status()
                        return r.json().get("data", {})
                    except Exception:
                        logger.warning("Failed to fetch detail for api %s", api_id)
                        return {}

            async with httpx.AsyncClient(timeout=30, limits=httpx.Limits(max_connections=20)) as detail_client:
                detail_tasks = [fetch_detail(detail_client, a["id"]) for a in apis_list]
                details = await asyncio.gather(*detail_tasks)

            # 按 folderId 分组接口（使用详情数据）
            groups: dict[int, list[dict]] = {}
            for api, detail in zip(apis_list, details):
                folder_id = api.get("folderId", 0)

                # 展开 requestBody jsonSchema 中的 $ref
                request_body = detail.get("requestBody")
                if isinstance(request_body, dict) and request_body.get("jsonSchema"):
                    request_body = {
                        **request_body,
                        "jsonSchema": self._resolve_refs(request_body["jsonSchema"]),
                    }

                # 展开每个 response jsonSchema 中的 $ref
                responses = detail.get("responses") or []
                resolved_responses = []
                for resp in responses:
                    if isinstance(resp, dict) and resp.get("jsonSchema"):
                        resp = {**resp, "jsonSchema": self._resolve_refs(resp["jsonSchema"])}
                    resolved_responses.append(resp)

                merged = {
                    "name": api.get("name", ""),
                    "method": api.get("method", ""),
                    "path": api.get("path", ""),
                    "status": api.get("status", ""),
                    "description": detail.get("description") or api.get("description", ""),
                    "parameters": detail.get("parameters"),
                    "requestBody": request_body,
                    "responses": resolved_responses or None,
                    "responseExamples": detail.get("responseExamples"),
                }
                groups.setdefault(folder_id, []).append(merged)

            synced_files = []
            total_endpoints = 0
            for folder_id, endpoints in groups.items():
                if not endpoints:
                    continue
                # 构建目录路径：base_dir / 顶层 / 二级 / 文件夹名/
                path_parts = self._get_folder_path(folder_id, folder_by_id)
                if not path_parts:
                    target_dir = base_dir / "未分组"
                else:
                    safe_parts = [self._sanitize_filename(p) for p in path_parts]
                    target_dir = base_dir / Path(*safe_parts)

                # 每个接口单独一个 md 文件
                for ep in endpoints:
                    file_path = self._write_group_file(ep["name"], [ep], target_dir)
                    synced_files.append(str(file_path.relative_to(base_dir)))
                    total_endpoints += 1

            self._update_sync_meta(synced_files, base_dir)
            logger.info("Apifox sync complete: %d groups, %d endpoints", len(synced_files), total_endpoints)

            # 同步 doc 类型文档（在同一个锁内执行，复用已有 client）
            doc_result = await self._sync_docs_inner(base_dir)
            return {"groups": len(synced_files), "endpoints": total_endpoints, "docs": doc_result["docs"]}


def create_sync_services() -> list[tuple[str, "ApifoxSyncService"]]:
    """Create ApifoxSyncService instances from environment variables.

    Reads APIFOX_PROJECTS in 'name:id' or 'name:id:onlineId' format.
    onlineId is the published-projects ID used for doc sync (defaults to project id).
    Returns list of (project_name, service) tuples, empty list if not configured.
    """
    token = os.getenv("APIFOX_TOKEN", "")
    projects_str = os.getenv("APIFOX_PROJECTS", "")
    if not token or not projects_str:
        logger.warning("APIFOX_TOKEN or APIFOX_PROJECTS not set, skipping Apifox sync")
        return []
    result = []
    for entry in projects_str.split(","):
        entry = entry.strip()
        parts = entry.split(":")
        if len(parts) < 2:
            logger.warning("Invalid APIFOX_PROJECTS entry (expected 'name:id' or 'name:id:onlineId'): %s", entry)
            continue
        name = parts[0].strip()
        project_id = parts[1].strip()
        online_id = parts[2].strip() if len(parts) >= 3 else None
        result.append((name, ApifoxSyncService(token=token, project_id=project_id, online_id=online_id)))
    return result
