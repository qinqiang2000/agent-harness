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


def build_description(root_cause: str, evidence: str, repair_plan: str, affected_services: list[str] | None = None) -> str:
    """把根因/证据/修复计划/受影响服务拼成 Linear 单 Markdown 描述。"""
    services_section = ""
    if affected_services:
        services_section = f"## 受影响服务\n" + "\n".join(f"- {s}" for s in affected_services) + "\n\n"
    return (
        f"## 根因\n{root_cause}\n\n"
        f"## 证据\n{evidence}\n\n"
        f"## 修复计划\n{repair_plan}\n\n"
        f"{services_section}"
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


async def _resolve_team_id(client, team_id: str) -> str:
    """team_id 为空或为团队 key（如 ARALGO）时，解析成 UUID。"""
    if not team_id:
        raise RuntimeError(
            "payload 缺少 team_key，请填写团队标识符（如 ARALGO、QUASAF）"
        )
    # 已经是 UUID 格式，直接用
    if "-" in team_id and len(team_id) > 30:
        return team_id
    # 当作 key 查找
    data = await client._query("{ teams { nodes { id name key } } }")
    nodes = data.get("teams", {}).get("nodes", [])
    key_upper = team_id.upper()
    for t in nodes:
        if t.get("key", "").upper() == key_upper:
            return t["id"]
    available = ", ".join(t.get("key", "") for t in nodes)
    raise RuntimeError(f"未找到团队 key={team_id!r}，可用: {available}")


async def list_teams_cmd(workspace_id: str = "") -> None:
    """列出 Linear 可用团队，输出 JSON 数组供 agent 展示给用户选择。"""
    client, _ = _make_linear_client(workspace_id)
    data = await client._query("{ teams { nodes { id name key } } }")
    nodes = data.get("teams", {}).get("nodes", [])
    teams = [{"key": t["key"], "name": t["name"], "id": t["id"]} for t in nodes]
    print(json.dumps(teams, ensure_ascii=False))


async def create_issue_cmd(input_path: str) -> None:
    """建 Linear 单 + 落 repair_runs(pending_review)，结果打到 stdout。"""
    from plugins.bundled.repair.store import RepairRun, Stage

    payload = load_payload(input_path)
    title = payload.get("title")
    if not title:
        raise ValueError("payload 缺少必填字段 'title'")
    # 优先取 team_key（标识符如 ARALGO），兼容旧的 team_id（UUID）
    team_key = payload.get("team_key") or payload.get("team_id", "")
    workspace_id = payload.get("workspace_id", "")

    client, workspace_id = _make_linear_client(workspace_id)
    team_id = await _resolve_team_id(client, team_key)

    affected_services = payload.get("affected_services", [])
    if isinstance(affected_services, str):
        affected_services = [s.strip() for s in affected_services.split(",") if s.strip()]

    description = build_description(
        payload.get("root_cause", ""),
        payload.get("evidence", ""),
        payload.get("repair_plan", ""),
        affected_services,
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
            repos=json.dumps(affected_services, ensure_ascii=False) if affected_services else "",
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


def acquire_lock_cmd(issue_id: str, identifier: str, repos_csv: str) -> None:
    """原子申请一组 repo 锁，结果打到 stdout（供 developer skill 解析）。

    成功：{"ok": true}；被占：{"ok": false, "blocked_by": "<占用方单号>"}。
    DB 异常：{"ok": false, "error": "..."}（agent 视同被挡，保守停止）。
    """
    repos = [r.strip() for r in repos_csv.split(",") if r.strip()]
    store = _make_store()
    ok, blocker = store.acquire_repos(issue_id, identifier, repos)
    if ok:
        print(json.dumps({"ok": True}, ensure_ascii=False))
    else:
        print(json.dumps({"ok": False, "blocked_by": blocker}, ensure_ascii=False))


def _make_jenkins_client():
    """构造真实 JenkinsClient（从 env 读配置）。"""
    from plugins.bundled.repair.jenkins_build_store import JenkinsBuildStore
    from plugins.bundled.repair.jenkins_client import JenkinsClient

    builds_db = os.getenv("JENKINS_BUILDS_DB_PATH", "data/repair/jenkins_builds.db")
    full = str(_ROOT / builds_db) if not os.path.isabs(builds_db) else builds_db
    build_store = JenkinsBuildStore(full)

    return JenkinsClient(
        base_url=os.getenv("JENKINS_BASE_URL", ""),
        user=os.getenv("JENKINS_USER", ""),
        api_token=os.getenv("JENKINS_API_TOKEN", ""),
        cicd_job=os.getenv("JENKINS_CICD_JOB", "cicd-pipeline"),
        cicd_token=os.getenv("JENKINS_CICD_TOKEN", ""),
        autotest_job=os.getenv("JENKINS_AUTOTEST_JOB", "at-automated-test"),
        autotest_token=os.getenv("JENKINS_AUTOTEST_TOKEN", ""),
        build_store=build_store,
    )


async def retrigger_build_cmd(issue_id: str) -> None:
    """重新触发构建+测试（门禁：stage∈{BUILDING,REJECTED} 且 branch 非空）。"""
    from plugins.bundled.repair.store import Stage

    store = _make_store()
    run = store.get(issue_id)
    if run is None:
        print(json.dumps({"ok": False, "error": f"找不到修复单 {issue_id}"}, ensure_ascii=False))
        return
    if run.stage not in (Stage.BUILDING, Stage.REJECTED):
        print(json.dumps(
            {"ok": False, "error": f"不可重跑：当前 stage={run.stage}，需为 building 或 rejected"},
            ensure_ascii=False,
        ))
        return
    if not run.branch:
        print(json.dumps({"ok": False, "error": "不可重跑：分支为空，开发尚未完成"}, ensure_ascii=False))
        return

    repos = json.loads(run.repos) if run.repos else ([run.repo] if run.repo else [])
    ok, blocker = store.acquire_repos(issue_id, run.linear_identifier, repos)
    if not ok:
        print(json.dumps(
            {"ok": False, "error": f"涉及的服务正被 {blocker} 占用，请稍后重试"},
            ensure_ascii=False,
        ))
        return

    jenkins = _make_jenkins_client()
    try:
        build_id = await jenkins.trigger_build(repos=repos, branch=run.branch)
        await jenkins.start_driver(build_id)
        store.update(issue_id, stage=Stage.BUILDING, jenkins_build_id=build_id)
        print(json.dumps({"ok": True, "build_id": build_id, "branch": run.branch}, ensure_ascii=False))
    except Exception as e:
        store.release_repos(issue_id)
        print(json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False))
    finally:
        await jenkins.aclose()


def main() -> None:
    parser = argparse.ArgumentParser(description="repair pipeline CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_list_teams = sub.add_parser("list-teams", help="列出可用 Linear 团队")
    p_list_teams.add_argument("--workspace", default="", help="workspace ID（可选）")
    p_create = sub.add_parser("create-issue", help="建 Linear bug 单")
    p_create.add_argument("--input", required=True, help="payload JSON 文件路径")
    p_lock = sub.add_parser("acquire-lock", help="原子申请一组 repo 锁")
    p_lock.add_argument("--issue", required=True, help="Linear issue UUID")
    p_lock.add_argument("--identifier", required=True, help="人类可读单号，如 ENG-7")
    p_lock.add_argument("--repos", required=True, help="逗号分隔的 project_id 列表")
    p_retrigger = sub.add_parser("retrigger-build", help="重新触发构建+测试")
    p_retrigger.add_argument("--issue", required=True, help="Linear issue UUID")
    args = parser.parse_args()

    if args.cmd == "list-teams":
        try:
            asyncio.run(list_teams_cmd(args.workspace))
        except Exception as e:
            print(json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False))
            sys.exit(1)
    elif args.cmd == "create-issue":
        try:
            asyncio.run(create_issue_cmd(args.input))
        except Exception as e:
            print(json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False))
            sys.exit(1)
    elif args.cmd == "acquire-lock":
        try:
            acquire_lock_cmd(args.issue, args.identifier, args.repos)
        except Exception as e:
            print(json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False))
            sys.exit(1)
    elif args.cmd == "retrigger-build":
        try:
            asyncio.run(retrigger_build_cmd(args.issue))
        except Exception as e:
            print(json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False))
            sys.exit(1)


if __name__ == "__main__":
    main()
