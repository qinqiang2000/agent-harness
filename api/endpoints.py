"""API route handlers."""

import logging
import json
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from sse_starlette.sse import EventSourceResponse
from .models.requests import QueryRequest
from .utils.context_storage import save_context
from .dependencies import get_agent_service, get_session_service


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["agent"])


@router.post("/query")
async def query_agent(request: Request):
    """
    通用 Agent 查询接口 - 支持任意 skill 的对话请求

    Args:
        request: FastAPI Request object for accessing HTTP request details

    Returns:
        Server-Sent Events (SSE) stream with agent responses

    Request Body (QueryRequest):
        - tenant_id: str (必填) - 租户ID
        - prompt: str (必填) - 用户请求
        - skill: str (可选) - Skill 名称，如 "customer-service"
        - language: str (新会话必填) - 响应语言，如 "中文", "English"
        - session_id: str (可选) - 会话ID，用于续接对话
        - context: str (可选) - 附加上下文数据
        - metadata: dict (可选) - 扩展元数据

    Examples:
        新会话 (需要 language):
        ```
        POST /api/query
        {
          "tenant_id": "1",
          "prompt": "如何配置开票模板？",
          "skill": "customer-service",
          "language": "中文",
          "session_id": null,
          "context": "订单号: 12345"
        }
        ```

        续接会话 (language 可选):
        ```
        POST /api/query
        {
          "tenant_id": "1",
          "prompt": "继续前面的对话",
          "session_id": "abc-123-def"
        }
        ```

    Response Stream:
        ```
        event: session_created
        data: {"session_id": "abc-123"}

        event: assistant_message
        data: {"content": "正在查找..."}

        event: tool_use
        data: {"tool": "Grep", "input": "..."}

        event: result
        data: {"session_id": "abc-123", "duration_ms": 1234, ...}
        ```

    Validation Rules:
        - 新会话 (session_id 为空): 必须提供 language
        - 续接会话 (session_id 存在): language 可选
    """
    try:
        # Parse and validate request body
        body = await request.json()
        
        try:
            query_request = QueryRequest(**body)
        except ValidationError as e:
            # Return 422 with detailed validation errors (industry best practice)
            errors = []
            for error in e.errors():
                field = ".".join(str(loc) for loc in error["loc"])
                errors.append({
                    "field": field,
                    "message": error["msg"],
                    "type": error["type"]
                })
            logger.warning(f"Validation error: {errors}")
            return JSONResponse(
                status_code=422,
                content={
                    "error": "Validation Error",
                    "message": "Request validation failed",
                    "details": errors
                }
            )
        
        # Print request body information
        request_dict = query_request.model_dump()
        # Log context partially if present (first 200 chars)
        log_dict = request_dict.copy()
        if log_dict.get("context"):
            context_preview = log_dict["context"][:200] + "..." if len(log_dict["context"]) > 200 else log_dict["context"]
            log_dict["context"] = f"[{len(request_dict['context'])} chars] {context_preview}"
        logger.info(f"Request body: {json.dumps(log_dict, ensure_ascii=False, indent=2)}")
        
        logger.info(
            f"Received query request: tenant={query_request.tenant_id}, "
            f"skill={query_request.skill}, session={query_request.session_id}"
        )

        # Save context if provided
        context_file_path = None
        if query_request.context:
            context_file_path = save_context(
                tenant_id=query_request.tenant_id,
                context=query_request.context
            )

        # Get service and process (dependency injection)
        agent_service = get_agent_service()

        return EventSourceResponse(
            agent_service.process_query(query_request, context_file_path=context_file_path),
            media_type="text/event-stream"
        )

    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in request body: {str(e)}")
        return JSONResponse(
            status_code=400,
            content={
                "error": "Bad Request",
                "message": "Invalid JSON in request body",
                "details": str(e)
            }
        )
    except Exception as e:
        logger.error(f"Error in query_agent: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "ai-agent-service"}


@router.post("/interrupt/{session_id}")
async def interrupt_session(session_id: str):
    """
    Interrupt an ongoing agent session.

    Args:
        session_id: The session ID to interrupt

    Returns:
        {"success": True} if session was found and interrupted
        {"success": False} if session doesn't exist or interrupt failed
    """
    logger.info(f"Received interrupt request for session: {session_id}")
    session_service = get_session_service()
    success = await session_service.interrupt(session_id)
    return {"success": success, "session_id": session_id}



