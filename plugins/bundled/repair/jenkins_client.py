"""Jenkins 客户端 —— 本期占位 mock。

签名按真实 Jenkins build API 设计：
  POST {JENKINS_URL}/job/{job}/buildWithParameters?BRANCH=...
  GET  {JENKINS_URL}/job/{job}/{build_no}/api/json  + testReport
联调时只改这里的实现，coordinator 不动。
"""

import logging
import uuid
from typing import Optional

logger = logging.getLogger(__name__)


class JenkinsClient:
    """触发构建 + 拉取测试报告。本期 mock，真实实现见各方法 TODO。"""

    def __init__(self, mock_ready: bool = True):
        """
        Args:
            mock_ready: 占位用——get_report 是否立即返回就绪报告。
                        真实实现会忽略此参数，按 Jenkins 实际状态返回。
        """
        self._mock_ready = mock_ready

    def trigger_build(self, repo: str, branch: str) -> str:
        """触发一次构建，返回 build_id。

        TODO(联调): 真实实现
          POST {JENKINS_URL}/job/{job_name}/buildWithParameters
            params: BRANCH={branch}, REPO={repo}
            auth: (JENKINS_USER, JENKINS_API_TOKEN)
          从 Location header 的 queue item 轮询拿到 build number 作为 build_id。

        Args:
            repo: 目标仓库（如 ai-agent/foo）
            branch: 修复分支名

        Returns:
            build_id（本期 mock 为随机 id）
        """
        build_id = f"mock-build-{uuid.uuid4().hex[:8]}"
        logger.info(
            "[Jenkins][MOCK] trigger_build repo=%s branch=%s -> %s",
            repo,
            branch,
            build_id,
        )
        return build_id

    def get_report(self, build_id: str) -> Optional[dict]:
        """拉取构建的测试报告；未就绪返回 None。

        TODO(联调): 真实实现
          GET {JENKINS_URL}/job/{job}/{build_no}/api/json -> 看 building/result
          building=true -> return None
          完成 -> GET .../testReport/api/json 解析 pass/fail，
                 组装 {"status": "...", "summary": "...", "failures": [...]}

        Args:
            build_id: trigger_build 返回的 id

        Returns:
            报告字典或 None（未就绪）
        """
        if not self._mock_ready:
            logger.info("[Jenkins][MOCK] get_report %s -> not ready", build_id)
            return None
        logger.info("[Jenkins][MOCK] get_report %s -> ready (mock pass)", build_id)
        return {
            "status": "success",
            "summary": "[MOCK] 3 passed, 0 failed",
            "failures": [],
        }
