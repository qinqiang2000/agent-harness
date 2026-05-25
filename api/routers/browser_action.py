"""Browser action router — accessibility tree analysis via agent session."""

import json
import logging
import re

import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["browser-action"])


class BrowserActionRequest(BaseModel):
    session_id: str = ""
    query: str = ""           # 首次调用时的用户意图，无 session 时必填
    page_tree: str
    url: str = ""
    title: str = ""
    completed_steps: list[int] = []
    last_actions: list[str] = []
    skill: str = "browser-interaction"


class ActionStep(BaseModel):
    step: int
    action: str
    ref: int
    value: str = ""
    description: str
    expect_navigation: bool = False
    expect_reserialize: bool = False
    expect_loading: bool = False
    auto_execute: bool = True


class BrowserActionResponse(BaseModel):
    session_id: str = ""
    steps: list[ActionStep]
    message: str = ""


def _parse_steps(text: str) -> list[dict]:
    clean = re.sub(r"```(?:json)?", "", text).strip()

    try:
        result = json.loads(clean)
        return result if isinstance(result, list) else [result]
    except json.JSONDecodeError:
        pass

    # 截断恢复：提取所有完整的 {...} 对象
    steps = []
    depth = 0
    start = -1
    for i, ch in enumerate(clean):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start != -1:
                try:
                    obj = json.loads(clean[start : i + 1])
                    steps.append(obj)
                except json.JSONDecodeError:
                    pass
                start = -1

    if steps:
        logger.warning(f"JSON truncated, recovered {len(steps)} steps")
        return steps

    raise ValueError(f"无法解析返回的 JSON: {text[:200]}")


async def _call_agent(
    base_url: str,
    prompt: str,
    skill: str,
    session_id: str = "",
) -> tuple[str, str]:
    """调用 agent，返回 (assistant完整文本, session_id)。"""
    payload: dict = {
        "tenant_id": "1",
        "prompt": prompt,
        "skill": skill,
    }
    if session_id:
        payload["session_id"] = session_id
    else:
        payload["language"] = "中文"

    full_text = ""
    returned_session_id = session_id

    async with httpx.AsyncClient(timeout=60) as client:
        async with client.stream("POST", f"{base_url}/api/query", json=payload) as resp:
            if resp.status_code != 200:
                raise HTTPException(status_code=502, detail=f"Agent 请求失败: {resp.status_code}")
            event_type = ""
            async for line in resp.aiter_lines():
                if line.startswith("event:"):
                    event_type = line[6:].strip()
                elif line.startswith("data:"):
                    try:
                        data = json.loads(line[5:].strip())
                        if event_type == "session_created":
                            returned_session_id = data.get("session_id", returned_session_id)
                        elif event_type == "assistant_message":
                            full_text += data.get("content", "")
                    except Exception:
                        pass

    return full_text, returned_session_id


def _build_prompt(
    page_tree: str,
    url: str,
    title: str,
    completed_steps: list[int],
    last_actions: list[str],
    query: str = "",
) -> str:
    if not completed_steps:
        query_line = f"用户意图：{query}\n\n" if query else ""
        return (
            f"{query_line}"
            f"请分析以下页面的 accessibility tree，生成完成操作所需的步骤。\n\n"
            f"当前页面 URL：{url}\n"
            f"当前页面标题：{title}\n\n"
            f"accessibility tree：\n{page_tree}"
        )

    last_actions_text = ""
    if last_actions:
        lines = "\n".join(f"- 步骤{i+1}：{desc}" for i, desc in enumerate(last_actions))
        last_actions_text = f"\n上一批已执行操作：\n{lines}\n"

    query_line = f"用户意图：{query}\n\n" if query else ""
    return (
        f"{query_line}"
        f"页面已更新，请基于新的 accessibility tree 继续规划剩余步骤。\n\n"
        f"已完成步骤编号：{completed_steps}"
        f"{last_actions_text}\n"
        f"当前页面 URL：{url}\n"
        f"当前页面标题：{title}\n\n"
        f"新的 accessibility tree：\n{page_tree}"
    )


@router.post("/browser-action", response_model=BrowserActionResponse)
async def browser_action(req: BrowserActionRequest, request: Request):
    """分析页面 accessibility tree，返回操作步骤。首次调用需传 query，后续续步传 completed_steps。"""
    if not req.page_tree:
        raise HTTPException(status_code=400, detail="page_tree 不能为空")
    if not req.session_id and not req.query:
        raise HTTPException(status_code=400, detail="首次调用需提供 query")

    base_url = str(request.base_url).rstrip("/")

    prompt = _build_prompt(req.page_tree, req.url, req.title, req.completed_steps, req.last_actions, req.query)
    full_text, session_id = await _call_agent(base_url, prompt, req.skill, req.session_id)

    if not full_text:
        raise HTTPException(status_code=502, detail="Agent 未返回内容")

    try:
        steps_data = _parse_steps(full_text)
        steps = [ActionStep(**{**s, "value": s.get("value") or ""}) for s in steps_data]
    except Exception:
        logger.warning(f"步骤解析失败，agent 返回自然语言: {full_text[:100]}")
        return BrowserActionResponse(session_id=session_id, steps=[], message=full_text)

    return BrowserActionResponse(session_id=session_id, steps=steps)
