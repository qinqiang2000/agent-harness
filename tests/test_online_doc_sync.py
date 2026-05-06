"""
验证通过在线文档地址（shared-docs / published-projects）同步接口和 doc 文档的可行性。

用法：
    # 只打印统计，不写文件
    python tests/test_online_doc_sync.py --online-id 9bd8b320-212e-455e-9048-3bff7150a458

    # 实际写文件到 /tmp/online_sync_out
    python tests/test_online_doc_sync.py --online-id 9bd8b320-212e-455e-9048-3bff7150a458 --sync --output /tmp/online_sync_out

    # published-projects 数字 ID（发票云标准版）
    python tests/test_online_doc_sync.py --online-id 3958968
"""

import argparse
import asyncio
import json
import logging
import re
from datetime import datetime
from pathlib import Path

import httpx

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

TOKEN = "afxp_e257b7b6286M1Jehyi1iOC9TgZm0mpUfwD0Q"
APIFOX_BASE = "https://api.apifox.com/api/v1"


def _api_base(online_id: str) -> str:
    """UUID 格式用 shared-docs，纯数字用 published-projects。"""
    if "-" in online_id:
        return f"{APIFOX_BASE}/shared-docs/{online_id}"
    return f"{APIFOX_BASE}/published-projects/{online_id}"


def _build_headers() -> dict:
    return {
        "Authorization": f"Bearer {TOKEN}",
        "X-Apifox-Api-Version": "2024-03-28",
    }


def _sanitize(name: str) -> str:
    return re.sub(r'[\s/\\:*?"<>|]', "_", name)


# ---------------------------------------------------------------------------
# 树遍历
# ---------------------------------------------------------------------------

def collect_nodes(nodes: list[dict], path_parts: list[str] | None = None) -> tuple[list[dict], list[dict]]:
    """递归收集 apiDetail 节点和 doc 节点，返回 (api_nodes, doc_nodes)。"""
    if path_parts is None:
        path_parts = []
    apis, docs = [], []
    for node in nodes:
        name = node.get("name", "")
        node_type = node.get("type", "")
        cur_parts = path_parts + [name]

        if node_type == "apiDetail":
            api = node.get("api") or {}
            if api.get("id"):
                apis.append({
                    "id": api["id"],
                    "name": name,
                    "path_parts": cur_parts,
                    "method": api.get("method", ""),
                    "path": api.get("path", ""),
                    "status": api.get("status", ""),
                })
        elif node_type == "doc":
            doc = node.get("doc") or {}
            if doc.get("id"):
                docs.append({"id": doc["id"], "name": name, "path_parts": cur_parts})

        if node_type != "doc":
            sub_apis, sub_docs = collect_nodes(node.get("children") or [], cur_parts)
            apis.extend(sub_apis)
            docs.extend(sub_docs)

    return apis, docs


# ---------------------------------------------------------------------------
# 拉取详情
# ---------------------------------------------------------------------------

async def fetch_api_detail(client: httpx.AsyncClient, api_base: str, api_id: int, sem: asyncio.Semaphore) -> dict:
    async with sem:
        try:
            r = await client.get(f"{api_base}/http-apis/{api_id}", headers=_build_headers())
            r.raise_for_status()
            return r.json().get("data") or {}
        except Exception as e:
            logger.warning("Failed to fetch api %s: %s", api_id, e)
            return {}


async def fetch_doc_content(client: httpx.AsyncClient, api_base: str, doc_id: int, sem: asyncio.Semaphore) -> str:
    async with sem:
        try:
            r = await client.get(f"{api_base}/doc/{doc_id}", headers=_build_headers())
            r.raise_for_status()
            return r.json().get("data", {}).get("content") or ""
        except Exception as e:
            logger.warning("Failed to fetch doc %s: %s", doc_id, e)
            return ""


# ---------------------------------------------------------------------------
# 写文件
# ---------------------------------------------------------------------------

def write_api_file(node: dict, detail: dict, output_dir: Path) -> Path:
    parts = node["path_parts"]
    target_dir = output_dir / Path(*[_sanitize(p) for p in parts[:-1]]) if len(parts) > 1 else output_dir
    target_dir.mkdir(parents=True, exist_ok=True)

    file_path = target_dir / f"{_sanitize(node['name'])}.md"
    lines = [
        f"# {node['name']}",
        "",
        f"> 自动同步自 Apifox 在线文档，最后更新：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        f"**方法**: `{node['method'].upper()}`  ",
        f"**路径**: `{node['path']}`  ",
        f"**状态**: {node['status']}",
        "",
    ]
    raw = {k: detail[k] for k in ["description", "parameters", "requestBody", "responses"] if detail.get(k)}
    if raw:
        lines += ["```json", json.dumps(raw, ensure_ascii=False, indent=2), "```"]

    file_path.write_text("\n".join(lines), encoding="utf-8")
    return file_path


def write_doc_file(node: dict, content: str, output_dir: Path) -> Path:
    parts = node["path_parts"]
    target_dir = output_dir / Path(*[_sanitize(p) for p in parts[:-1]]) if len(parts) > 1 else output_dir
    target_dir.mkdir(parents=True, exist_ok=True)

    file_path = target_dir / f"{_sanitize(node['name'])}.md"
    header = f"# {node['name']}\n\n> 自动同步自 Apifox 在线文档，最后更新：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
    file_path.write_text(header + content, encoding="utf-8")
    return file_path


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

async def run(online_id: str, sync: bool, output: str) -> None:
    api_base = _api_base(online_id)
    logger.info("API base: %s", api_base)

    # 1. 拉取目录树
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(f"{api_base}/http-api-tree", headers=_build_headers())
        if r.status_code == 404:
            print(f"\n❌ {online_id} 没有在线文档站（404），跳过")
            return
        r.raise_for_status()
        tree = r.json().get("data") or []

    api_nodes, doc_nodes = collect_nodes(tree)
    logger.info("Found %d api nodes, %d doc nodes", len(api_nodes), len(doc_nodes))

    if not sync:
        # 只打印统计 + 抽样验证
        print(f"\n{'='*60}")
        print(f"online_id  : {online_id}")
        print(f"api_base   : {api_base}")
        print(f"接口数量    : {len(api_nodes)}")
        print(f"doc 数量    : {len(doc_nodes)}")

        print(f"\n--- 前 5 个接口 ---")
        for n in api_nodes[:5]:
            print(f"  {n['method'].upper():6} {n['path']:50} [{n['status']}]")
            print(f"         路径: {'/'.join(n['path_parts'])}")

        print(f"\n--- 前 5 个 doc ---")
        for n in doc_nodes[:5]:
            print(f"  {'/'.join(n['path_parts'])}")

        # 抽样验证接口详情
        if api_nodes:
            sample = api_nodes[0]
            sem = asyncio.Semaphore(1)
            async with httpx.AsyncClient(timeout=30) as client:
                detail = await fetch_api_detail(client, api_base, sample["id"], sem)
            print(f"\n--- 接口详情抽样（{sample['name']}）---")
            print(f"  description  : {str(detail.get('description', ''))[:100]}")
            print(f"  requestBody  : {list((detail.get('requestBody') or {}).keys())}")
            print(f"  responses    : {len(detail.get('responses') or [])} 个")
            print(f"  parameters   : {list((detail.get('parameters') or {}).keys())}")

        # 抽样验证 doc 内容
        if doc_nodes:
            sample = doc_nodes[0]
            sem = asyncio.Semaphore(1)
            async with httpx.AsyncClient(timeout=30) as client:
                content = await fetch_doc_content(client, api_base, sample["id"], sem)
            print(f"\n--- doc 内容抽样（{sample['name']}）---")
            print(content[:400])

        print(f"\n结论：{'✅ 可行，接口和 doc 均可通过在线文档地址同步' if api_nodes or doc_nodes else '❌ 无数据'}")
        return

    # 2. 实际同步写文件
    output_dir = Path(output)
    output_dir.mkdir(parents=True, exist_ok=True)
    sem = asyncio.Semaphore(10)

    async with httpx.AsyncClient(timeout=30, limits=httpx.Limits(max_connections=10)) as client:
        api_details = await asyncio.gather(*[fetch_api_detail(client, api_base, n["id"], sem) for n in api_nodes])
        doc_contents = await asyncio.gather(*[fetch_doc_content(client, api_base, n["id"], sem) for n in doc_nodes])

    api_written = sum(1 for node, detail in zip(api_nodes, api_details) if detail and write_api_file(node, detail, output_dir))
    doc_written = sum(1 for node, content in zip(doc_nodes, doc_contents) if content and write_doc_file(node, content, output_dir))

    print(f"\n{'='*60}")
    print(f"同步完成：接口 {api_written} 个，doc {doc_written} 个")
    print(f"输出目录：{output_dir.resolve()}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="验证在线文档同步接口和 doc 的可行性")
    parser.add_argument("--online-id", required=True, help="shared-docs UUID 或 published-projects 数字 ID")
    parser.add_argument("--sync", action="store_true", help="实际写文件（默认只打印统计和抽样）")
    parser.add_argument("--output", default="data/kb-new", help="输出目录（--sync 时生效）")
    args = parser.parse_args()

    asyncio.run(run(args.online_id, args.sync, args.output))
