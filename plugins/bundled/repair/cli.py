"""agent 调用入口：create-issue 子命令。

issue-diagnosis agent 判 bug + 用户同意后调用：
  $AGENTS_ROOT/.venv/bin/python plugins/bundled/repair/cli.py create-issue --input /tmp/repair/payload.json

stdout 输出单行 JSON：{"ok": true, "identifier": "ENG-7", "issue_id": "..."}
"""

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

# 用 PYTHONPATH=$AGENTS_ROOT 引仓库模块（与现有 hooks 同源）
_ROOT = Path(__file__).resolve().parents[3]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def load_payload(path: str) -> dict:
    """读 payload JSON 文件。"""
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def build_description(root_cause: str, evidence: str, repair_plan: str) -> str:
    """把根因/证据/修复计划拼成 Linear 单 Markdown 描述。"""
    return (
        f"## 根因\n{root_cause}\n\n"
        f"## 证据\n{evidence}\n\n"
        f"## 修复计划\n{repair_plan}\n\n"
        f"---\n_本单由 issue-diagnosis 自动诊断生成，待审核后进入自动修复流水线。_"
    )


def _make_linear_client(workspace_id: str):
    """构造 LinearClient（取 token）。返回 (client, workspace_id)。"""
    from plugins.bundled.linear.token_store import TokenStore

    db_path = os.getenv("LINEAR_TOKEN_DB", "data/linear/linear_tokens.db")
    ts = TokenStore(str(_ROOT / db_path) if not os.path.isabs(db_path) else db_path)
    ws = workspace_id or ts.get_first_workspace_id()
    token = ts.get_token(ws) if ws else None
    if not token:
        raise RuntimeError(f"no Linear token for workspace={ws}")
    from plugins.bundled.linear.linear_client import LinearClient

    return LinearClient(token), ws


def _make_store():
    from plugins.bundled.repair.store import RepairStore

    db_path = os.getenv("REPAIR_DB_PATH", "data/repair/repair_runs.db")
    full = str(_ROOT / db_path) if not os.path.isabs(db_path) else db_path
    return RepairStore(full)


async def create_issue_cmd(input_path: str) -> None:
    """建 Linear 单 + 落 repair_runs(pending_review)，结果打到 stdout。"""
    from plugins.bundled.repair.store import RepairRun, Stage

    payload = load_payload(input_path)
    title = payload.get("title")
    if not title:
        raise ValueError("payload 缺少必填字段 'title'")
    team_id = payload.get("team_id", "")
    workspace_id = payload.get("workspace_id", "")

    client, workspace_id = _make_linear_client(workspace_id)

    description = build_description(
        payload.get("root_cause", ""),
        payload.get("evidence", ""),
        payload.get("repair_plan", ""),
    )

    issue = await client.create_issue(
        team_id=team_id, title=title, description=description
    )

    store = _make_store()
    store.upsert(
        RepairRun(
            linear_issue_id=issue["id"],
            linear_identifier=issue.get("identifier", ""),
            workspace_id=workspace_id,
            stage=Stage.PENDING_REVIEW,
            repo=payload.get("repo", ""),
            root_cause=payload.get("root_cause", ""),
            repair_plan=payload.get("repair_plan", ""),
            evidence=payload.get("evidence", ""),
        )
    )

    print(
        json.dumps(
            {
                "ok": True,
                "identifier": issue.get("identifier", ""),
                "issue_id": issue["id"],
                "url": issue.get("url", ""),
            },
            ensure_ascii=False,
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="repair pipeline CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_create = sub.add_parser("create-issue", help="建 Linear bug 单")
    p_create.add_argument("--input", required=True, help="payload JSON 文件路径")
    args = parser.parse_args()

    if args.cmd == "create-issue":
        try:
            asyncio.run(create_issue_cmd(args.input))
        except Exception as e:
            print(json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False))
            sys.exit(1)


if __name__ == "__main__":
    main()
