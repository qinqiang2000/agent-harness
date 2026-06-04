"""Linear GraphQL API 异步客户端（精简版）。"""

import logging
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)

_LINEAR_API_URL = "https://api.linear.app/graphql"
_RETRY_ATTEMPTS = 3


class LinearAPIError(Exception):
    """Linear API 调用异常。"""

    def __init__(self, message: str, errors: Optional[list] = None):
        super().__init__(message)
        self.errors = errors or []


class LinearClient:
    """Linear GraphQL API 异步客户端。

    封装常用的 Agent Activity / Issue 操作，支持自动重试。
    """

    def __init__(self, access_token: str):
        self._token = access_token
        self._headers = {
            "Authorization": access_token,
            "Content-Type": "application/json",
        }

    async def _query(
        self, query: str, variables: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """执行 GraphQL 请求，失败自动指数退避重试。

        Args:
            query: GraphQL query/mutation 字符串
            variables: 变量字典（可选）

        Returns:
            GraphQL data 字段内容

        Raises:
            LinearAPIError: 请求失败或 GraphQL 返回 errors
        """
        payload = {"query": query}
        if variables:
            payload["variables"] = variables

        last_exc = None
        for attempt in range(_RETRY_ATTEMPTS):
            try:
                async with httpx.AsyncClient(timeout=30) as client:
                    resp = await client.post(
                        _LINEAR_API_URL, json=payload, headers=self._headers
                    )
                    resp.raise_for_status()
                    data = resp.json()
                    if "errors" in data:
                        raise LinearAPIError(
                            f"GraphQL errors: {data['errors']}", errors=data["errors"]
                        )
                    return data.get("data", {})
            except LinearAPIError:
                raise
            except Exception as e:
                last_exc = e
                if attempt < _RETRY_ATTEMPTS - 1:
                    import asyncio

                    await asyncio.sleep(2**attempt)
                    logger.warning(f"[Linear] API retry {attempt + 1}: {e}")

        raise LinearAPIError(
            f"API call failed after {_RETRY_ATTEMPTS} attempts"
        ) from last_exc

    # ── Viewer ───────────────────────────────────────────────────────────────

    async def get_viewer(self) -> Dict[str, Any]:
        """获取当前 token 对应的用户及 workspace 信息。

        Returns:
            包含 id/name/email/organization 的字典
        """
        data = await self._query("""
            query {
                viewer {
                    id name email
                    organization { id name }
                }
            }
        """)
        return data["viewer"]

    # ── Agent Activity ───────────────────────────────────────────────────────

    async def _create_activity(
        self, session_id: str, content: Dict[str, Any], ephemeral: bool = False
    ) -> str:
        """创建 AgentActivity，返回 activity ID。

        Args:
            session_id: AgentSession ID
            content: activity content 字典（含 type 字段）
            ephemeral: 是否为临时消息（不持久化）

        Returns:
            新建 activity 的 ID
        """
        input_data: Dict[str, Any] = {
            "agentSessionId": session_id,
            "content": content,
        }
        if ephemeral:
            input_data["ephemeral"] = True

        data = await self._query(
            """
            mutation AgentActivityCreate($input: AgentActivityCreateInput!) {
                agentActivityCreate(input: $input) {
                    success
                    agentActivity { id }
                }
            }
            """,
            {"input": input_data},
        )
        return data["agentActivityCreate"]["agentActivity"]["id"]

    async def send_thought(
        self, session_id: str, body: str, ephemeral: bool = False
    ) -> str:
        """发送 thought 类型 activity（Agent 内部思考）。

        Args:
            session_id: AgentSession ID
            body: 思考内容文本
            ephemeral: 是否临时

        Returns:
            activity ID
        """
        return await self._create_activity(
            session_id, {"type": "thought", "body": body}, ephemeral=ephemeral
        )

    async def send_response(self, session_id: str, body: str) -> str:
        """发送 response 类型 activity（对用户的正式回复）。

        Args:
            session_id: AgentSession ID
            body: 回复内容文本

        Returns:
            activity ID
        """
        return await self._create_activity(
            session_id, {"type": "response", "body": body}
        )

    async def send_error(self, session_id: str, body: str) -> str:
        """发送 error 类型 activity。

        Args:
            session_id: AgentSession ID
            body: 错误描述文本

        Returns:
            activity ID
        """
        return await self._create_activity(session_id, {"type": "error", "body": body})

    # ── Agent Session ────────────────────────────────────────────────────────

    async def update_agent_session(
        self,
        session_id: str,
        plan: Optional[List[Dict]] = None,
        external_urls: Optional[List[Dict]] = None,
    ) -> None:
        """更新 AgentSession 的 plan 或 externalUrls。

        Args:
            session_id: AgentSession ID
            plan: plan 步骤列表，每项含 content/status 字段
            external_urls: 外部链接列表，每项含 label/url 字段
        """
        input_data: Dict[str, Any] = {}
        if plan is not None:
            input_data["plan"] = plan
        if external_urls is not None:
            input_data["externalUrls"] = external_urls
        if not input_data:
            return
        await self._query(
            """
            mutation AgentSessionUpdate($id: String!, $input: AgentSessionUpdateInput!) {
                agentSessionUpdate(id: $id, input: $input) { success }
            }
            """,
            {"id": session_id, "input": input_data},
        )

    # ── Issue ────────────────────────────────────────────────────────────────

    async def get_issue(self, issue_id: str) -> Dict[str, Any]:
        """获取 Issue 详情。

        Args:
            issue_id: Linear Issue UUID

        Returns:
            包含 id/identifier/title/description/team/state/assignee/delegate 的字典
        """
        data = await self._query(
            """
            query Issue($id: String!) {
                issue(id: $id) {
                    id identifier title description
                    team { id name }
                    state { id name type }
                    assignee { id name }
                    delegate { id name }
                    priority priorityLabel
                }
            }
            """,
            {"id": issue_id},
        )
        issue = data["issue"]
        if issue.get("assignee"):
            issue["assigneeId"] = issue["assignee"]["id"]
        if issue.get("delegate"):
            issue["delegateId"] = issue["delegate"]["id"]
        return issue

    async def update_issue(
        self,
        issue_id: str,
        state_id: Optional[str] = None,
        delegate_id: Optional[str] = None,
        description: Optional[str] = None,
    ) -> None:
        """更新 Issue 状态/委派/描述。

        Args:
            issue_id: Linear Issue UUID
            state_id: 新状态 ID（可选）
            delegate_id: 委派的 user/bot ID（可选）
            description: 新描述内容（可选）
        """
        input_data: Dict[str, Any] = {}
        if state_id:
            input_data["stateId"] = state_id
        if delegate_id:
            input_data["delegateId"] = delegate_id
        if description is not None:
            input_data["description"] = description
        if not input_data:
            return
        await self._query(
            """
            mutation IssueUpdate($id: String!, $input: IssueUpdateInput!) {
                issueUpdate(id: $id, input: $input) { success }
            }
            """,
            {"id": issue_id, "input": input_data},
        )

    # ── Team ─────────────────────────────────────────────────────────────────

    async def get_team_first_started_state_id(self, team_id: str) -> Optional[str]:
        """获取团队 workflow 中第一个 started 类型状态的 ID。

        Args:
            team_id: Linear team ID

        Returns:
            state ID 或 None
        """
        data = await self._query(
            """
            query TeamStates($teamId: String!) {
                team(id: $teamId) {
                    states { nodes { id name type position } }
                }
            }
            """,
            {"teamId": team_id},
        )
        states = data["team"]["states"]["nodes"]
        started = [s for s in states if s["type"] == "started"]
        if not started:
            return None
        return min(started, key=lambda s: s["position"])["id"]
