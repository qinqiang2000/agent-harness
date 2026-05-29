"""Linear channel plugin entry point."""

import logging
import os
import secrets
from typing import Any, Dict, Optional

import httpx
from fastapi import APIRouter, BackgroundTasks, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from api.plugins.api import PluginAPI
from api.plugins.channel import ChannelCapabilities, ChannelMeta, ChannelPlugin

from plugins.bundled.linear.handler import LinearSessionHandler
from plugins.bundled.linear.token_store import TokenStore
from plugins.bundled.linear.webhook_verifier import verify_linear_webhook

logger = logging.getLogger(__name__)

# CSRF state 临时存储（单进程，单 workspace 场景足够）
_oauth_states: Dict[str, bool] = {}


class LinearChannelPlugin(ChannelPlugin):
    """Linear Agent channel plugin."""

    def __init__(self, api: PluginAPI):
        self.api = api
        self.config = api.config

        db_path = self.config.get("token_db_path", "data/linear/linear_tokens.db")
        self.token_store = TokenStore(db_path)

        self.handler = LinearSessionHandler(
            agent_service=api.agent_service,
            token_store=self.token_store,
            config=self.config,
        )

    def get_meta(self) -> ChannelMeta:
        return ChannelMeta(
            id="linear",
            name="Linear Agent",
            webhook_path="/linear/webhook",
            description="Linear Agent 集成，接收 Webhook 并调用 product-workflow 生成 PRD",
        )

    def get_capabilities(self) -> ChannelCapabilities:
        return ChannelCapabilities(
            send_text=False,
            send_images=False,
            send_cards=False,
            receive_webhook=True,
            session_management=True,
            transfer_human=False,
        )

    def create_router(self) -> APIRouter:
        router = APIRouter(tags=["linear"])
        handler = self.handler
        token_store = self.token_store

        @router.post("/linear/webhook")
        async def linear_webhook(request: Request, background_tasks: BackgroundTasks):
            """接收 Linear AgentSession Webhook，5 秒内返回 200。"""
            raw_body = await request.body()
            signature = request.headers.get("linear-signature", "")
            webhook_secret = os.environ.get("LINEAR_WEBHOOK_SECRET", "")

            payload_json = {}
            try:
                import json

                payload_json = json.loads(raw_body)
            except Exception:
                return JSONResponse(status_code=400, content={"error": "invalid json"})

            timestamp_ms = payload_json.get("webhookTimestamp", 0)

            if webhook_secret and not verify_linear_webhook(
                raw_body, signature, webhook_secret, timestamp_ms
            ):
                logger.warning("[Linear] Webhook signature verification failed")
                return JSONResponse(
                    status_code=401, content={"error": "invalid signature"}
                )

            event_type = payload_json.get("type", "")
            action = payload_json.get("action", "")

            logger.info(
                f"[Linear] Webhook received: type={event_type}, action={action}, payload={payload_json}"
            )

            if event_type in ("AgentSession", "AgentSessionEvent"):
                if action == "created":
                    background_tasks.add_task(handler.handle_created, payload_json)
                elif action == "prompted":
                    background_tasks.add_task(handler.handle_prompted, payload_json)
                elif action in ("stopped", "stop"):
                    background_tasks.add_task(handler.handle_stopped, payload_json)

            return JSONResponse(status_code=200, content={"ok": True})

        @router.get("/linear/oauth/install")
        async def linear_oauth_install():
            """引导 workspace 管理员完成 OAuth 授权。"""
            client_id = os.environ.get("LINEAR_CLIENT_ID", "")
            redirect_uri = os.environ.get("LINEAR_REDIRECT_URI", "")
            if not client_id or not redirect_uri:
                return HTMLResponse(
                    "<h3>LINEAR_CLIENT_ID 或 LINEAR_REDIRECT_URI 未配置</h3>",
                    status_code=500,
                )

            state = secrets.token_urlsafe(32)
            _oauth_states[state] = True

            auth_url = (
                "https://linear.app/oauth/authorize"
                f"?client_id={client_id}"
                f"&redirect_uri={redirect_uri}"
                "&response_type=code"
                "&actor=app"
                "&scope=read,write,app:assignable,app:mentionable"
                f"&state={state}"
            )
            return RedirectResponse(url=auth_url)

        @router.get("/linear/oauth/callback")
        async def linear_oauth_callback(
            code: str = "", state: str = "", error: str = ""
        ):
            """OAuth 回调，换取 token 并存储。"""
            if error:
                return HTMLResponse(f"<h3>授权失败：{error}</h3>", status_code=400)

            if not state or state not in _oauth_states:
                return HTMLResponse(
                    "<h3>无效的 state 参数，请重新安装</h3>", status_code=400
                )
            _oauth_states.pop(state, None)

            client_id = os.environ.get("LINEAR_CLIENT_ID", "")
            client_secret = os.environ.get("LINEAR_CLIENT_SECRET", "")
            redirect_uri = os.environ.get("LINEAR_REDIRECT_URI", "")

            # 换取 token
            try:
                async with httpx.AsyncClient(timeout=15) as http:
                    resp = await http.post(
                        "https://api.linear.app/oauth/token",
                        data={
                            "code": code,
                            "redirect_uri": redirect_uri,
                            "client_id": client_id,
                            "client_secret": client_secret,
                            "grant_type": "authorization_code",
                        },
                    )
                    resp.raise_for_status()
                    token_data = resp.json()
            except Exception as e:
                logger.error(f"[Linear] OAuth token exchange failed: {e}")
                return HTMLResponse(f"<h3>Token 换取失败：{e}</h3>", status_code=500)

            access_token = token_data.get("access_token", "")
            refresh_token = token_data.get("refresh_token")
            expires_in = token_data.get("expires_in")
            scopes = token_data.get("scope", "")

            # 获取 app_user_id 和 workspace 信息
            try:
                from plugins.bundled.linear.linear_client import LinearClient

                lc = LinearClient(access_token)
                viewer = await lc.get_viewer()
                app_user_id = viewer["id"]
                workspace_id = viewer["organization"]["id"]
                workspace_name = viewer["organization"]["name"]
            except Exception as e:
                logger.error(f"[Linear] Failed to fetch viewer info: {e}")
                return HTMLResponse(f"<h3>获取用户信息失败：{e}</h3>", status_code=500)

            token_store.save_installation(
                workspace_id=workspace_id,
                workspace_name=workspace_name,
                app_user_id=app_user_id,
                access_token=access_token,
                refresh_token=refresh_token,
                expires_in=expires_in,
                scopes=scopes,
            )

            logger.info(
                f"[Linear] OAuth installation complete: workspace={workspace_name} ({workspace_id})"
            )
            return HTMLResponse(
                f"<h3>✅ Linear Agent 安装成功！</h3>"
                f"<p>Workspace：{workspace_name}</p>"
                f"<p>App User ID：{app_user_id}</p>"
                f"<p>现在可以在 Linear 中 @提及 Agent 或将 Issue 分配给 Agent 了。</p>"
            )

        @router.get("/linear/stats")
        async def linear_stats():
            """返回安装状态统计（调试用）。"""
            ws_id = token_store.get_first_workspace_id()
            if not ws_id:
                return {"installed": False}
            row = token_store.get_installation(ws_id)
            return {
                "installed": True,
                "workspace_id": ws_id,
                "workspace_name": row["workspace_name"] if row else None,
                "app_user_id": row["app_user_id"] if row else None,
            }

        return router

    async def send_text(
        self,
        recipient_id: str,
        text: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> bool:
        return False  # Linear 通过 AgentActivity 通信，不走 send_text

    async def on_start(self) -> None:
        logger.info("[Linear] Linear channel plugin started")

    async def on_stop(self) -> None:
        logger.info("[Linear] Linear channel plugin stopped")


def register(api: PluginAPI) -> LinearChannelPlugin:
    plugin = LinearChannelPlugin(api)
    router = plugin.create_router()
    api.register_router(router)
    logger.info("[Linear] Linear plugin registered")
    return plugin
