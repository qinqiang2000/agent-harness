"""Linear GraphQL API client."""

import logging
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)

_LINEAR_API_URL = "https://api.linear.app/graphql"
_RETRY_ATTEMPTS = 3


class LinearAPIError(Exception):
    def __init__(self, message: str, errors: Optional[list] = None):
        super().__init__(message)
        self.errors = errors or []


class LinearClient:
    """Linear GraphQL API 异步客户端。"""

    def __init__(self, access_token: str):
        self._token = access_token
        self._headers = {
            "Authorization": access_token,
            "Content-Type": "application/json",
        }

    async def _query(
        self, query: str, variables: Optional[Dict] = None
    ) -> Dict[str, Any]:
        payload = {"query": query}
        if variables:
            payload["variables"] = variables

        last_exc = None
        for attempt in range(_RETRY_ATTEMPTS):
            try:
                async with httpx.AsyncClient(timeout=30) as client:
                    resp = await client.post(
                        _LINEAR_API_URL,
                        json=payload,
                        headers=self._headers,
                    )
                    resp.raise_for_status()
                    data = resp.json()
                    if "errors" in data:
                        raise LinearAPIError(
                            f"GraphQL errors: {data['errors']}",
                            errors=data["errors"],
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

    # ── Viewer ──────────────────────────────────────────────────────────────

    async def get_viewer(self) -> Dict[str, Any]:
        data = await self._query("""
            query {
                viewer {
                    id
                    name
                    email
                    organization { id name }
                }
            }
        """)
        return data["viewer"]

    # ── Agent Activity ───────────────────────────────────────────────────────

    async def create_agent_activity(
        self,
        session_id: str,
        content: Dict[str, Any],
        ephemeral: bool = False,
    ) -> str:
        data = await self._query(
            """
            mutation AgentActivityCreate($input: AgentActivityCreateInput!) {
                agentActivityCreate(input: $input) {
                    success
                    agentActivity { id }
                }
            }
        """,
            {
                "input": {
                    "agentSessionId": session_id,
                    "content": content,
                    **({"ephemeral": True} if ephemeral else {}),
                }
            },
        )
        return data["agentActivityCreate"]["agentActivity"]["id"]

    async def send_thought(
        self, session_id: str, body: str, ephemeral: bool = False
    ) -> str:
        return await self.create_agent_activity(
            session_id, {"type": "thought", "body": body}, ephemeral=ephemeral
        )

    async def send_action(
        self,
        session_id: str,
        action: str,
        parameter: str = "",
        result: str = "",
        ephemeral: bool = True,
    ) -> str:
        content: Dict[str, Any] = {"type": "action", "action": action}
        if parameter:
            content["parameter"] = parameter
        if result:
            content["result"] = result
        return await self.create_agent_activity(
            session_id, content, ephemeral=ephemeral
        )

    async def send_response(self, session_id: str, body: str) -> str:
        return await self.create_agent_activity(
            session_id, {"type": "response", "body": body}
        )

    async def send_error(self, session_id: str, body: str) -> str:
        return await self.create_agent_activity(
            session_id, {"type": "error", "body": body}
        )

    async def send_elicitation(
        self,
        session_id: str,
        body: str,
        signal: Optional[str] = None,
        signal_metadata: Optional[Dict] = None,
    ) -> str:
        input_data: Dict[str, Any] = {
            "agentSessionId": session_id,
            "content": {"type": "elicitation", "body": body},
        }
        if signal:
            input_data["signal"] = signal
        if signal_metadata:
            input_data["signalMetadata"] = signal_metadata
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

    # ── Agent Session ────────────────────────────────────────────────────────

    async def update_agent_session(
        self,
        session_id: str,
        plan: Optional[List[Dict]] = None,
        external_urls: Optional[List[Dict]] = None,
    ) -> None:
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

    async def get_agent_session_activities(self, session_id: str) -> List[Dict]:
        data = await self._query(
            """
            query AgentSession($id: String!) {
                agentSession(id: $id) {
                    activities {
                        edges {
                            node {
                                updatedAt
                                content {
                                    ... on AgentActivityThoughtContent { body }
                                    ... on AgentActivityActionContent { action parameter result }
                                    ... on AgentActivityElicitationContent { body }
                                    ... on AgentActivityResponseContent { body }
                                    ... on AgentActivityErrorContent { body }
                                    ... on AgentActivityPromptContent { body }
                                }
                            }
                        }
                    }
                }
            }
        """,
            {"id": session_id},
        )
        edges = data.get("agentSession", {}).get("activities", {}).get("edges", [])
        return [e["node"] for e in edges]

    # ── Issue ────────────────────────────────────────────────────────────────

    async def get_issue(self, issue_id: str) -> Dict[str, Any]:
        data = await self._query(
            """
            query Issue($id: String!) {
                issue(id: $id) {
                    id identifier title description
                    team { id name }
                    state { id name type }
                    assignee { id name }
                    delegate { id name }
                    parent { id identifier }
                    priority priorityLabel
                }
            }
        """,
            {"id": issue_id},
        )
        issue = data["issue"]
        # 补充 assigneeId / delegateId 便于上层直接使用
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

    async def create_issue(
        self,
        team_id: str,
        title: str,
        description: str = "",
        parent_id: Optional[str] = None,
        state_id: Optional[str] = None,
        priority: Optional[int] = None,
        label_ids: Optional[List[str]] = None,
        project_id: Optional[str] = None,
        assignee_id: Optional[str] = None,
        delegate_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        input_data: Dict[str, Any] = {
            "teamId": team_id,
            "title": title,
            "description": description,
        }
        if parent_id:
            input_data["parentId"] = parent_id
        if state_id:
            input_data["stateId"] = state_id
        if priority is not None:
            input_data["priority"] = priority
        if label_ids:
            input_data["labelIds"] = label_ids
        if project_id:
            input_data["projectId"] = project_id
        if assignee_id:
            input_data["assigneeId"] = assignee_id
        if delegate_id:
            input_data["delegateId"] = delegate_id

        data = await self._query(
            """
            mutation IssueCreate($input: IssueCreateInput!) {
                issueCreate(input: $input) {
                    success
                    issue { id identifier url title }
                }
            }
        """,
            {"input": input_data},
        )
        return data["issueCreate"]["issue"]

    async def create_issue_relation(
        self,
        issue_id: str,
        related_issue_id: str,
        relation_type: str = "blocks",
    ) -> None:
        await self._query(
            """
            mutation IssueRelationCreate($input: IssueRelationCreateInput!) {
                issueRelationCreate(input: $input) { success }
            }
        """,
            {
                "input": {
                    "issueId": issue_id,
                    "relatedIssueId": related_issue_id,
                    "type": relation_type,
                }
            },
        )

    # ── Team ─────────────────────────────────────────────────────────────────

    async def get_team_states(self, team_id: str) -> List[Dict]:
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
        return data["team"]["states"]["nodes"]

    async def get_team_state_by_name(self, team_id: str, name: str) -> Optional[str]:
        states = await self.get_team_states(team_id)
        for s in states:
            if s["name"] == name:
                return s["id"]
        return None

    async def get_team_first_started_state_id(self, team_id: str) -> Optional[str]:
        states = await self.get_team_states(team_id)
        started = [s for s in states if s["type"] == "started"]
        if not started:
            return None
        return min(started, key=lambda s: s["position"])["id"]

    # ── Labels ───────────────────────────────────────────────────────────────

    async def get_or_create_label(self, team_id: str, name: str) -> str:
        data = await self._query(
            """
            query IssueLabels($teamId: ID!, $name: String!) {
                issueLabels(filter: { team: { id: { eq: $teamId } }, name: { eq: $name } }) {
                    nodes { id name }
                }
            }
        """,
            {"teamId": team_id, "name": name},
        )
        nodes = data["issueLabels"]["nodes"]
        if nodes:
            return nodes[0]["id"]
        # 创建新标签
        create_data = await self._query(
            """
            mutation IssueLabelCreate($input: IssueLabelCreateInput!) {
                issueLabelCreate(input: $input) {
                    success
                    issueLabel { id }
                }
            }
        """,
            {"input": {"teamId": team_id, "name": name}},
        )
        return create_data["issueLabelCreate"]["issueLabel"]["id"]

    # ── Project ──────────────────────────────────────────────────────────────

    async def get_project_by_name(self, team_id: str, name: str) -> Optional[str]:
        data = await self._query(
            """
            query Projects($teamId: String!) {
                team(id: $teamId) {
                    projects { nodes { id name } }
                }
            }
        """,
            {"teamId": team_id},
        )
        for p in data["team"]["projects"]["nodes"]:
            if p["name"] == name:
                return p["id"]
        return None

    # ── Attachment ───────────────────────────────────────────────────────────

    async def create_attachment(
        self,
        issue_id: str,
        url: str,
        title: str,
        subtitle: Optional[str] = None,
    ) -> str:
        input_data: Dict[str, Any] = {
            "issueId": issue_id,
            "url": url,
            "title": title,
        }
        if subtitle:
            input_data["subtitle"] = subtitle
        data = await self._query(
            """
            mutation AttachmentCreate($input: AttachmentCreateInput!) {
                attachmentCreate(input: $input) {
                    success
                    attachment { id }
                }
            }
        """,
            {"input": input_data},
        )
        return data["attachmentCreate"]["attachment"]["id"]
