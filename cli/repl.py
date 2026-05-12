"""REPL core loop."""

import asyncio
import json
import logging
from pathlib import Path

from prompt_toolkit import PromptSession
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.history import FileHistory
from rich.console import Console
from rich.panel import Panel

from api.dependencies import get_agent_service, get_config_service
from cli.command_handler import CommandHandler
from cli.keyboard_listener import KeyboardListener
from cli.state import REPLState
from cli.stream_renderer import StreamRenderer

logger = logging.getLogger(__name__)

# Global console
console = Console(
    legacy_windows=False,
    force_terminal=True,
    force_interactive=False,
    no_color=False,
    tab_size=4
)

# Log directory
LOG_DIR = Path(__file__).parent.parent / "log"
LOG_DIR.mkdir(exist_ok=True)


async def process_stream(agent_service, request, renderer, state):
    """处理流式响应

    Args:
        agent_service: Agent 服务实例
        request: 查询请求
        renderer: 输出渲染器
        state: REPL 状态
    """
    interrupted = False
    keyboard_listener = KeyboardListener()

    try:
        async for message in agent_service.process_query(request):
            # Check if ESC was pressed
            if not interrupted and keyboard_listener.check_esc():
                interrupted = True
                # Call interrupt on session service
                if state.session_id and agent_service.session_service:
                    success = await agent_service.session_service.interrupt(state.session_id)
                    if success:
                        renderer.show_interrupted()
                        logger.info("User interrupted session")
                    else:
                        logger.warning("Failed to interrupt session")
                break

            event_type = message.get("event")
            data = message.get("data")

            # Skip heartbeat events
            if event_type == "heartbeat":
                continue

            # Parse data if it's JSON
            try:
                data_obj = json.loads(data) if isinstance(data, str) else data
            except json.JSONDecodeError:
                data_obj = {"raw": data}

            # Handle different event types
            if event_type == "session_created":
                session_id = data_obj.get("session_id")
                if session_id:
                    state.set_session(session_id)
                    renderer.on_session_created(session_id)

            elif event_type == "assistant_message":
                content = data_obj.get("content", "")
                renderer.print_text(content)

            elif event_type == "result":
                renderer.on_result(data_obj)

            elif event_type == "error":
                renderer.show_error(data_obj)

    except Exception as e:
        # Don't show error if it's just an interrupt cleanup issue
        error_msg = str(e)
        if not ("cancel scope" in error_msg.lower() or interrupted):
            renderer.show_error({"message": str(e), "type": type(e).__name__})
            logger.exception("Stream processing error")
        else:
            logger.info(f"Stream ended: {type(e).__name__}")
    finally:
        keyboard_listener.restore()


class REPLRunner:
    """REPL 运行器

    封装 REPL 主循环逻辑。
    """

    def __init__(self, skill: str = "customer-service"):
        """初始化 REPL 运行器

        Args:
            skill: 要使用的skill名称
        """
        self.agent_service = get_agent_service()
        self.config_service = get_config_service()
        self.state = REPLState(skill=skill)
        self.renderer = StreamRenderer()
        self.command_handler = CommandHandler(self.state, self.config_service)

    def _show_welcome(self):
        """显示欢迎消息"""
        current_model = self.config_service.get_current_config_name()
        model_config = self.config_service.get_current_config()

        console.print(Panel.fit(
            "[bold cyan]AI Agent CLI 调试工具[/bold cyan]\n"
            f"[green]模型配置:[/green] {current_model} ({model_config.description})\n"
            f"[green]Skill:[/green] {self.state.skill}\n"
            "输入 /help 查看帮助，/config 查看配置，/q 退出",
            border_style="blue"
        ))
        console.print()

    def _build_prompt(self) -> HTML:
        """构建提示符

        Returns:
            HTML 格式的提示符
        """
        if self.state.session_id:
            return HTML(
                f'<ansicyan>[{self.state.session_id[:8]}]</ansicyan> <b>You></b> '
            )
        else:
            return HTML('<b>You></b> ')

    async def _process_query(self, user_input: str):
        """处理用户查询

        Args:
            user_input: 用户输入
        """
        request = self.state.build_request(user_input)
        self.renderer.start_response()
        await process_stream(self.agent_service, request, self.renderer, self.state)

    async def run(self):
        """主循环"""
        # Setup command history (persistent across sessions)
        history_file = LOG_DIR / ".cli_history"
        session = PromptSession(history=FileHistory(str(history_file)))

        # Show welcome message
        self._show_welcome()

        # Main loop
        while True:
            try:
                # Get user input
                user_input = await session.prompt_async(self._build_prompt())

                # Skip empty input
                if not user_input.strip():
                    continue

                # Handle special commands
                if user_input.startswith("/"):
                    should_continue = await self.command_handler.handle(user_input)
                    if not should_continue:
                        break
                    continue

                # Process query
                await self._process_query(user_input)

            except asyncio.CancelledError:
                # Interrupt during stream can cancel the prompt, just continue
                print()  # New line after interrupted prompt
                continue

            except KeyboardInterrupt:
                print("\n\033[33m(使用 /q 退出)\033[0m\n")
                continue

            except EOFError:
                print("\n\033[33mbye bye!\033[0m")
                break

            except Exception as e:
                print(f"\033[31m错误: {str(e)}\033[0m\n")
                logger.exception("REPL error")
