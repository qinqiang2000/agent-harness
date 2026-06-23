#!/usr/bin/env python3
"""code-fix skill 的 CICD + autotest 触发脚本（同步版）。

从 code-fix Step 7 输出文本中解析仓库/分支，并行触发所有服务的 cicd-pipeline，
全部成功后触发 at-automated-test。

用法（由 SKILL.md Step 8 通过 Bash 调用）：
    python run_cicd.py "<fix_result_文本>"
    python run_cicd.py --file /tmp/fix_result.txt

环境变量（可覆盖默认值）：
    JENKINS_BASE_URL      Jenkins 服务器地址
    JENKINS_USER          HTTP Basic Auth 用户名
    JENKINS_API_TOKEN     HTTP Basic Auth 密码/Token
    JENKINS_CICD_TOKEN    cicd-pipeline 触发 token
    JENKINS_AUTOTEST_TOKEN at-automated-test 触发 token
"""

import argparse
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Optional, Tuple

import requests

# ── Jenkins 配置（优先读环境变量）────────────────────────────────────────────
BASE_URL = os.environ.get("JENKINS_BASE_URL", "http://jump-test.piaozone.com:8080")
AUTH = (
    os.environ.get("JENKINS_USER", "chuang_li"),
    os.environ.get("JENKINS_API_TOKEN", "110a928885da4fe07b6b06b95a33a37d9b"),
)
CICD_TOKEN = os.environ.get("JENKINS_CICD_TOKEN", "410xCyjlF88nE63t")
AUTOTEST_TOKEN = os.environ.get("JENKINS_AUTOTEST_TOKEN", "JAaZnYeyAeHXN5eN")

# 轮询间隔和超时
QUEUE_POLL_INTERVAL = 3
CICD_POLL_INTERVAL = 15
AUTOTEST_POLL_INTERVAL = 30
QUEUE_TIMEOUT = 120
CICD_TIMEOUT = 600
AUTOTEST_TIMEOUT = 3600

# 解析 code-fix 输出中的仓库和分支
_REPO_RE = re.compile(r"仓库[：:]\s*(\S+)")
_BRANCH_RE = re.compile(r"分支[：:]\s*(\S+)")
_SERVICE_RE = re.compile(r"[^/]+$")


def parse_targets(fix_result: str) -> List[Tuple[str, str]]:
    """从 code-fix 输出文本中提取所有 (service, branch) 对。

    Args:
        fix_result: code-fix Step 7 输出的修复结论文本

    Returns:
        [(service_name, branch), ...] 列表，service_name 取仓库路径最后一段
    """
    repos = _REPO_RE.findall(fix_result)
    branches = _BRANCH_RE.findall(fix_result)
    pairs = []
    for repo, branch in zip(repos, branches):
        m = _SERVICE_RE.search(repo)
        service = m.group(0) if m else repo
        pairs.append((service, branch))
    return pairs


def _get_queue_id(location: str) -> str:
    """从 Location 响应头中提取队列 ID。

    Args:
        location: Location 响应头值，形如 .../queue/item/29412/

    Returns:
        队列 ID 字符串

    Raises:
        ValueError: 无法解析队列 ID
    """
    m = re.search(r"/queue/item/(\d+)/", location)
    if not m:
        raise ValueError(f"Cannot parse queue id from: {location}")
    return m.group(1)


def _wait_build_number(queue_id: str) -> int:
    """轮询队列直到分配到构建号。

    Args:
        queue_id: Jenkins 队列 ID

    Returns:
        构建号

    Raises:
        TimeoutError: 超出 QUEUE_TIMEOUT 仍未分配
    """
    elapsed = 0
    while elapsed < QUEUE_TIMEOUT:
        time.sleep(QUEUE_POLL_INTERVAL)
        elapsed += QUEUE_POLL_INTERVAL
        try:
            data = requests.get(
                f"{BASE_URL}/queue/item/{queue_id}/api/json", auth=AUTH, timeout=15
            ).json()
            exe = data.get("executable")
            if exe:
                return exe["number"]
        except Exception as e:
            print(f"  [warn] Queue poll error (retry): {e}", flush=True)
    raise TimeoutError(f"Queue {queue_id} not assigned within {QUEUE_TIMEOUT}s")


def _poll_build(job_path: str, build_number: int, interval: int, timeout: int) -> dict:
    """轮询构建状态直到完成。

    Args:
        job_path: Job 路径，如 /job/cicd-pipeline
        build_number: Jenkins 构建号
        interval: 轮询间隔（秒）
        timeout: 最长等待时间（秒）

    Returns:
        最终构建 JSON 数据

    Raises:
        TimeoutError: 超出 timeout 仍未完成
    """
    elapsed = 0
    url = f"{BASE_URL}{job_path}/{build_number}/api/json"
    while elapsed < timeout:
        time.sleep(interval)
        elapsed += interval
        try:
            data = requests.get(url, auth=AUTH, timeout=15).json()
            if not data.get("building", True):
                return data
        except Exception as e:
            print(f"  [warn] Build poll error (retry): {e}", flush=True)
    raise TimeoutError(f"Build {build_number} not completed within {timeout}s")


def run_cicd(service: str, branch: str) -> dict:
    """触发单个服务的 cicd-pipeline 并等待结果。

    Args:
        service: 服务名，如 api-invoice-recognition
        branch: 构建分支，如 fixbug_20240612123456

    Returns:
        {"service": str, "build": int, "result": str, "success": bool, "url": str}
    """
    print(f"  → 触发构建: {service} @ {branch}", flush=True)
    resp = requests.post(
        f"{BASE_URL}/job/cicd-pipeline/buildWithParameters",
        auth=AUTH,
        params={
            "token": CICD_TOKEN,
            "SERVICE": service,
            "BRANCH": branch,
            "DEPLOY": "true",
        },
        timeout=30,
    )
    if resp.status_code != 201:
        raise RuntimeError(f"Trigger failed for {service}: HTTP {resp.status_code}")

    queue_id = _get_queue_id(resp.headers.get("Location", ""))
    build_number = _wait_build_number(queue_id)
    print(f"  → [{service}] 构建号: #{build_number}", flush=True)

    data = _poll_build(
        "/job/cicd-pipeline", build_number, CICD_POLL_INTERVAL, CICD_TIMEOUT
    )
    result = data.get("result", "UNKNOWN")
    console_url = f"{BASE_URL}/job/cicd-pipeline/{build_number}/consoleText"
    icon = "✅" if result == "SUCCESS" else "❌"
    print(f"  {icon} [{service}] #{build_number} {result}", flush=True)
    return {
        "service": service,
        "build": build_number,
        "result": result,
        "success": result == "SUCCESS",
        "url": console_url,
    }


def run_autotest(run_mode: str = "full", threads: int = 4) -> dict:
    """触发 at-automated-test 并等待结果。

    Args:
        run_mode: full 或 smoke
        threads: 并发线程数

    Returns:
        {"build": int, "result": str, "success": bool, "url": str}
    """
    print(f"\n🧪 触发自动化测试（mode={run_mode}, threads={threads}）...", flush=True)
    resp = requests.post(
        f"{BASE_URL}/job/at-automated-test/buildWithParameters",
        auth=AUTH,
        params={
            "token": AUTOTEST_TOKEN,
            "RUN_MODE": run_mode,
            "THREADS": str(threads),
        },
        timeout=30,
    )
    if resp.status_code != 201:
        raise RuntimeError(f"Autotest trigger failed: HTTP {resp.status_code}")

    queue_id = _get_queue_id(resp.headers.get("Location", ""))
    build_number = _wait_build_number(queue_id)
    print(f"  → 自动化测试构建号: #{build_number}", flush=True)

    data = _poll_build(
        "/job/at-automated-test", build_number, AUTOTEST_POLL_INTERVAL, AUTOTEST_TIMEOUT
    )
    result = data.get("result", "UNKNOWN")
    console_url = f"{BASE_URL}/job/at-automated-test/{build_number}/consoleText"
    icon = "✅" if result == "SUCCESS" else "❌"
    print(f"  {icon} 自动化测试 #{build_number} {result}", flush=True)
    return {
        "build": build_number,
        "result": result,
        "success": result == "SUCCESS",
        "url": console_url,
    }


def main(fix_result: str) -> int:
    """主流程：解析目标 → 并行 CICD → autotest。

    Args:
        fix_result: code-fix 输出的修复结论文本

    Returns:
        退出码，0 表示全部成功，1 表示有失败
    """
    targets = parse_targets(fix_result)
    if not targets:
        print("⚠️  未能从修复结论中解析到仓库/分支信息，跳过 CICD。", flush=True)
        print(
            "请确认修复结论中包含「仓库：xxx」和「分支：xxx」格式的信息。", flush=True
        )
        return 1

    print(f"\n🔨 开始并行构建 {len(targets)} 个服务：", flush=True)
    for svc, br in targets:
        print(f"   {svc} @ {br}", flush=True)

    # 并行触发所有 CICD
    cicd_results = []
    with ThreadPoolExecutor(max_workers=len(targets)) as executor:
        futures = {executor.submit(run_cicd, svc, br): svc for svc, br in targets}
        for future in as_completed(futures):
            svc = futures[future]
            try:
                cicd_results.append(future.result())
            except Exception as e:
                print(f"  ❌ [{svc}] 异常: {e}", flush=True)
                cicd_results.append(
                    {
                        "service": svc,
                        "build": 0,
                        "result": "EXCEPTION",
                        "success": False,
                        "url": "",
                    }
                )

    # 汇总 CICD 结果
    print("\n── CICD 构建汇总 ──────────────────────────────", flush=True)
    all_success = True
    for r in cicd_results:
        icon = "✅" if r["success"] else "❌"
        print(f"  {icon} {r['service']}  #{r['build']}  {r['result']}", flush=True)
        if r["url"]:
            print(f"     日志: {r['url']}", flush=True)
        if not r["success"]:
            all_success = False

    if not all_success:
        failed = [r["service"] for r in cicd_results if not r["success"]]
        print(
            f"\n⚠️  以下服务构建未成功，跳过自动化测试：{', '.join(failed)}", flush=True
        )
        return 1

    # 全部成功，触发 autotest
    try:
        at = run_autotest()
        print("\n── 自动化测试汇总 ─────────────────────────────", flush=True)
        icon = "✅" if at["success"] else "❌"
        print(f"  {icon} #{at['build']}  {at['result']}", flush=True)
        print(f"     日志: {at['url']}", flush=True)
        return 0 if at["success"] else 1
    except Exception as e:
        print(f"\n❌ 自动化测试异常: {e}", flush=True)
        return 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="触发 CICD + autotest")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("fix_result", nargs="?", help="code-fix 输出文本（直接传入）")
    group.add_argument("--file", help="包含 code-fix 输出文本的文件路径")
    args = parser.parse_args()

    if args.file:
        with open(args.file, encoding="utf-8") as f:
            text = f.read()
        # 读完立即删除临时文件，避免外部 rm 与进程启动产生竞争
        try:
            os.remove(args.file)
        except OSError:
            pass
    else:
        text = args.fix_result or ""

    if not text.strip():
        print("错误：fix_result 为空", flush=True)
        sys.exit(1)

    sys.exit(main(text))
