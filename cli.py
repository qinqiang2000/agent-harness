#!/usr/bin/env python
"""
AI Agent Service - Interactive CLI Debug Tool

Usage:
    python cli.py

Features:
    - Interactive REPL with session continuity
    - Real-time streaming output with incremental printing
    - Special commands (/quit, /new, /sessions, etc.)
    - Session history management
"""

import asyncio
import json
import logging
import sys
import select
from datetime import datetime
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

# Load environment variables FIRST (before importing project modules)
load_dotenv('.env.prod')

from prompt_toolkit import PromptSession
from prompt_toolkit.formatted_text import HTML
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

# Import project modules
from api.dependencies import get_agent_service, get_config_service
from api.models.requests import QueryRequest

# Configure logging - 分离系统日志和CLI输出
# 创建logs目录（如果不存在）
log_dir = Path(__file__).parent / "logs"
log_dir.mkdir(exist_ok=True)

# 配置根logger
root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)

# 文件handler - 记录所有INFO及以上级别的日志
file_handler = logging.FileHandler(
    log_dir / f"cli_{datetime.now().strftime('%Y%m%d')}.log",
    encoding='utf-8'
)
file_handler.setLevel(logging.INFO)
file_formatter = logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
file_handler.setFormatter(file_formatter)

# 控制台handler - 只显示WARNING及以上级别（避免INFO日志污染CLI输出）
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.WARNING)
console_formatter = logging.Formatter('%(levelname)s: %(message)s')
console_handler.setFormatter(console_formatter)

# 添加handlers
root_logger.addHandler(file_handler)
root_logger.addHandler(console_handler)

logger = logging.getLogger(__name__)

# Global console
console = Console()


class REPLState:
    """REPL state management."""

    def __init__(self):
        self.session_id: Optional[str] = None
        self.tenant_id: str = "cli-debug"
        self.language: str = "中文"
        self.skill: str = "customer-service"  # 默认使用客服skill
        self.session_history: list = []

    def build_request(self, prompt: str) -> QueryRequest:
        """Build QueryRequest with proper validation."""
        return QueryRequest(
            tenant_id=self.tenant_id,
            prompt=prompt,
            skill=self.skill,  # 添加skill参数
            language=self.language if not self.session_id else None,
            session_id=self.session_id,
            metadata={"source": "cli"}
        )

    def set_session(self, session_id: str):
        """Save session ID."""
        self.session_id = session_id
        self.session_history.append({
            "session_id": session_id,
            "created_at": datetime.now().isoformat()
        })

    def clear_session(self):
        """Clear session to start new conversation."""
        self.session_id = None


class StreamRenderer:
    """简单的输出渲染器"""

    def start_response(self):
        """开始响应"""
        print("💡 按 ESC 键可中断响应")

    def print_text(self, text: str):
        """打印文本"""
        if text:
            print(text)

    def on_session_created(self, session_id: str):
        """会话创建"""
        print(f"✓ 会话已创建: {session_id[:16]}...")

    def on_result(self, result: dict):
        """完成"""
        duration = result.get("duration_ms", 0) / 1000
        print(f"✓ 完成 ({duration:.1f}s)\n")

    def show_error(self, error: dict):
        """错误"""
        print(f"✗ 错误: {error.get('message')}\n")

    def show_interrupted(self):
        """中断"""
        print("⚠ 响应已中断\n")


def setup_keyboard_listener():
    """Setup non-blocking keyboard listener that doesn't interfere with output."""
    import termios
    import tty

    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)

    def check_esc() -> bool:
        """Check if ESC was pressed (non-blocking). Returns True if ESC detected."""
        try:
            rlist, _, _ = select.select([sys.stdin], [], [], 0)
            if rlist:
                # Temporarily set cbreak to read single char
                tty.setcbreak(fd)
                try:
                    char = sys.stdin.read(1)
                    return ord(char) == 27  # ESC key
                finally:
                    termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        except Exception:
            pass
        return False

    def restore():
        """Restore terminal settings."""
        try:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        except Exception:
            pass

    return check_esc, restore


async def process_stream(agent_service, request, renderer, state):
    """Process streaming response from AgentService."""
    interrupted = False
    check_esc, restore_term = setup_keyboard_listener()

    try:
        async for message in agent_service.process_query(request):
            # Check if ESC was pressed
            if not interrupted and check_esc():
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
        renderer.show_error({"message": str(e), "type": type(e).__name__})
        logger.exception("Stream processing error")
    finally:
        restore_term()


async def handle_command(cmd: str, state: REPLState, config_service=None) -> bool:
    """Handle special commands. Returns True to continue REPL loop."""
    if cmd in ["/q", "/quit", "/exit"]:
        console.print("[yellow]bye bye![/yellow]")
        return False

    elif cmd == "/new":
        state.clear_session()
        console.print("[green]✓ new session started[/green]\n")

    elif cmd == "/sessions":
        if not state.session_history:
            console.print("[yellow]暂无会话历史[/yellow]\n")
        else:
            table = Table(title="会话历史")
            table.add_column("Session ID", style="cyan")
            table.add_column("创建时间")
            for session in state.session_history:
                table.add_row(
                    session["session_id"][:20] + "...",
                    session["created_at"]
                )
            console.print(table)
            console.print()

    elif cmd.startswith("/tenant "):
        tenant_id = cmd.split(maxsplit=1)[1]
        state.tenant_id = tenant_id
        console.print(f"[green]✓ 租户ID已设置为: {tenant_id}[/green]\n")

    elif cmd.startswith("/lang "):
        language = cmd.split(maxsplit=1)[1]
        state.language = language
        console.print(f"[green]✓ 语言已设置为: {language}[/green]\n")

    elif cmd.startswith("/skill "):
        skill = cmd.split(maxsplit=1)[1]
        state.skill = skill
        console.print(f"[green]✓ Skill已设置为: {skill}[/green]\n")

    elif cmd == "/config":
        from api.constants import AGENTS_ROOT, DATA_DIR

        # Get current model config
        current_model = "未知"
        model_desc = "未知"
        base_url = "未知"
        if config_service:
            current_model = config_service.get_current_config_name()
            model_config = config_service.get_current_config()
            model_desc = model_config.description
            base_url = model_config.base_url

        console.print(Panel(
            f"[bold cyan]模型配置:[/bold cyan]\n"
            f"  [cyan]配置名称:[/cyan] {current_model}\n"
            f"  [cyan]描述:[/cyan] {model_desc}\n"
            f"  [cyan]Base URL:[/cyan] {base_url}\n\n"
            f"[bold cyan]会话配置:[/bold cyan]\n"
            f"  [cyan]租户ID:[/cyan] {state.tenant_id}\n"
            f"  [cyan]语言:[/cyan] {state.language}\n"
            f"  [cyan]Skill:[/cyan] {state.skill}\n"
            f"  [cyan]会话ID:[/cyan] {state.session_id or '(新会话)'}\n\n"
            f"[dim]工作目录:[/dim] {AGENTS_ROOT}\n"
            f"[dim]数据目录:[/dim] {DATA_DIR}",
            title="当前配置",
            border_style="blue"
        ))
        console.print()

    elif cmd == "/help":
        help_text = """[bold]可用命令:[/bold]
  /q, /quit, /exit    退出CLI
  /new                开始新会话
  /sessions           显示会话历史
  /tenant <id>        设置租户ID
  /lang <language>    设置响应语言
  /skill <name>       设置Skill (默认: customer-service)
  /config             显示当前配置（包括工作目录）
  /help               显示此帮助

[bold]快捷键:[/bold]
  ESC                 中断当前 LLM 响应

[bold]默认配置:[/bold]
  Skill: customer-service (可访问知识库回答业务问题)
  租户ID: cli-debug
  语言: 中文"""
        console.print(Panel(help_text, title="帮助", border_style="blue"))
        console.print()

    else:
        console.print(f"[red]未知命令: {cmd}[/red]")
        console.print("[dim]输入 /help 查看帮助[/dim]\n")

    return True


async def run_repl():
    """Main REPL loop."""
    # Initialize components
    agent_service = get_agent_service()
    config_service = get_config_service()
    state = REPLState()
    session = PromptSession()
    renderer = StreamRenderer()

    # Get current model config
    current_model = config_service.get_current_config_name()
    model_config = config_service.get_current_config()

    # Welcome message
    console.print(Panel.fit(
        "[bold cyan]AI Agent CLI 调试工具[/bold cyan]\n"
        f"[green]模型配置:[/green] {current_model} ({model_config.description})\n"
        f"[green]模式:[/green] 客服助手 (customer-service)\n"
        "输入 /help 查看帮助，/config 查看配置，/q 退出",
        border_style="blue"
    ))
    console.print()

    # Main loop
    while True:
        try:
            # Dynamic prompt based on session state
            if state.session_id:
                prompt_msg = HTML(
                    f'<ansicyan>[{state.session_id[:8]}]</ansicyan> <b>You></b> '
                )
            else:
                prompt_msg = HTML('<b>You></b> ')

            # Get user input
            user_input = await session.prompt_async(prompt_msg)

            # Skip empty input
            if not user_input.strip():
                continue

            # Handle special commands
            if user_input.startswith("/"):
                should_continue = await handle_command(user_input, state, config_service)
                if not should_continue:
                    break
                continue

            # Build request
            request = state.build_request(user_input)

            # Process query with streaming
            renderer.start_response()
            await process_stream(agent_service, request, renderer, state)

        except KeyboardInterrupt:
            console.print("\n[yellow](使用 /q 退出)[/yellow]\n")
            continue

        except EOFError:
            console.print("\n[yellow]bye bye![/yellow]")
            break

        except Exception as e:
            console.print(f"[red]错误: {str(e)}[/red]\n")
            logger.exception("REPL error")


if __name__ == "__main__":
    try:
        asyncio.run(run_repl())
    except KeyboardInterrupt:
        console.print("\n[yellow]interrupted[/yellow]")
        sys.exit(0)
