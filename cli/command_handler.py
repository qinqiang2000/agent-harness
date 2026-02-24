"""Command handler with command pattern."""

from typing import Dict, Optional

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from cli.state import REPLState

console = Console(
    legacy_windows=False,
    force_terminal=True,
    force_interactive=False,
    no_color=False,
    tab_size=4
)


class CommandHandler:
    """命令处理器

    使用命令模式消除长 if-elif 链，提高可维护性。
    """

    def __init__(self, state: REPLState, config_service):
        """初始化命令处理器

        Args:
            state: REPL 状态
            config_service: 配置服务
        """
        self.state = state
        self.config_service = config_service
        self.commands = self._register_commands()

    def _register_commands(self) -> Dict[str, callable]:
        """注册命令映射（消除长 if-elif 链）

        Returns:
            命令前缀到处理函数的映射
        """
        return {
            "/q": self._cmd_quit,
            "/quit": self._cmd_quit,
            "/exit": self._cmd_quit,
            "/new": self._cmd_new_session,
            "/sessions": self._cmd_list_sessions,
            "/tenant": self._cmd_set_tenant,
            "/lang": self._cmd_set_language,
            "/skill": self._cmd_set_skill,
            "/config": self._cmd_show_config,
            "/env": self._cmd_show_env,
            "/help": self._cmd_help,
        }

    async def handle(self, cmd: str) -> bool:
        """处理命令

        Args:
            cmd: 用户输入的命令

        Returns:
            是否继续 REPL 循环
        """
        # 根据命令前缀找到对应处理器
        for prefix, handler in self.commands.items():
            if cmd.startswith(prefix):
                return await handler(cmd)

        # 未知命令
        print(f"\033[31m未知命令: {cmd}\033[0m")
        print("\033[2m输入 /help 查看帮助\033[0m\n")
        return True

    async def _cmd_quit(self, cmd: str) -> bool:
        """退出命令"""
        print("\033[33mbye bye!\033[0m")
        return False

    async def _cmd_new_session(self, cmd: str) -> bool:
        """新会话命令"""
        self.state.clear_session()
        print("\033[32m✓ new session started\033[0m\n")
        return True

    async def _cmd_list_sessions(self, cmd: str) -> bool:
        """列出会话历史命令"""
        if not self.state.session_history:
            print("\033[33m暂无会话历史\033[0m\n")
        else:
            table = Table(title="会话历史")
            table.add_column("Session ID", style="cyan")
            table.add_column("创建时间")
            for session in self.state.session_history:
                table.add_row(
                    session["session_id"][:20] + "...",
                    session["created_at"]
                )
            console.print(table)
            console.print()
        return True

    async def _cmd_set_tenant(self, cmd: str) -> bool:
        """设置租户 ID 命令"""
        parts = cmd.split(maxsplit=1)
        if len(parts) < 2:
            print("\033[31m用法: /tenant <id>\033[0m\n")
            return True

        tenant_id = parts[1]
        self.state.tenant_id = tenant_id
        print(f"\033[32m✓ 租户ID已设置为: {tenant_id}\033[0m\n")
        return True

    async def _cmd_set_language(self, cmd: str) -> bool:
        """设置语言命令"""
        parts = cmd.split(maxsplit=1)
        if len(parts) < 2:
            print("\033[31m用法: /lang <language>\033[0m\n")
            return True

        language = parts[1]
        self.state.language = language
        print(f"\033[32m✓ 语言已设置为: {language}\033[0m\n")
        return True

    async def _cmd_set_skill(self, cmd: str) -> bool:
        """设置 Skill 命令"""
        parts = cmd.split(maxsplit=1)
        if len(parts) < 2:
            print("\033[31m用法: /skill <name>\033[0m\n")
            return True

        skill = parts[1]
        self.state.skill = skill
        print(f"\033[32m✓ Skill已设置为: {skill}\033[0m\n")
        return True

    async def _cmd_show_config(self, cmd: str) -> bool:
        """显示配置命令"""
        from api.constants import AGENTS_ROOT, DATA_DIR

        # Get current model config
        current_model = "未知"
        model_desc = "未知"
        base_url = "未知"
        if self.config_service:
            current_model = self.config_service.get_current_config_name()
            model_config = self.config_service.get_current_config()
            model_desc = model_config.description
            base_url = model_config.base_url

        console.print(Panel(
            f"[bold cyan]模型配置:[/bold cyan]\n"
            f"  [cyan]配置名称:[/cyan] {current_model}\n"
            f"  [cyan]描述:[/cyan] {model_desc}\n"
            f"  [cyan]Base URL:[/cyan] {base_url}\n\n"
            f"[bold cyan]会话配置:[/bold cyan]\n"
            f"  [cyan]租户ID:[/cyan] {self.state.tenant_id}\n"
            f"  [cyan]语言:[/cyan] {self.state.language}\n"
            f"  [cyan]Skill:[/cyan] {self.state.skill}\n"
            f"  [cyan]会话ID:[/cyan] {self.state.session_id or '(新会话)'}\n\n"
            f"[dim]工作目录:[/dim] {AGENTS_ROOT}\n"
            f"[dim]数据目录:[/dim] {DATA_DIR}",
            title="当前配置",
            border_style="blue"
        ))
        console.print()
        return True

    async def _cmd_show_env(self, cmd: str) -> bool:
        """显示环境变量命令"""
        import os

        # Get environment snapshot from config_service
        env_snapshot = {}
        if self.config_service:
            env_snapshot = self.config_service.get_current_env_snapshot()

        # Build display table
        table = Table(title="相关环境变量", show_header=True, header_style="bold cyan")
        table.add_column("变量名", style="cyan", no_wrap=True)
        table.add_column("值", style="white")

        # Critical variables (always show)
        critical_vars = [
            ("DEFAULT_MODEL_CONFIG", os.getenv("DEFAULT_MODEL_CONFIG", "(未设置)")),
        ]

        # Model-specific auth tokens
        auth_vars = [
            ("CLAUDE_CODE_OAUTH_TOKEN", self._mask_token(os.getenv("CLAUDE_CODE_OAUTH_TOKEN"))),
            ("ANTHROPIC_API_KEY", self._mask_token(os.getenv("ANTHROPIC_API_KEY"))),
            ("ANTHROPIC_AUTH_TOKEN", self._mask_token(os.getenv("ANTHROPIC_AUTH_TOKEN"))),
            ("GLM_AUTH_TOKEN", self._mask_token(os.getenv("GLM_AUTH_TOKEN"))),
            ("CLAUDE_ROUTER_AUTH_TOKEN", self._mask_token(os.getenv("CLAUDE_ROUTER_AUTH_TOKEN"))),
            ("LITELLM_API_KEY", self._mask_token(os.getenv("LITELLM_API_KEY"))),
        ]

        # Proxy settings
        proxy_vars = [
            ("CLAUDE_PROXY", os.getenv("CLAUDE_PROXY", "(未设置)")),
            ("CLAUDE_ROUTER_PROXY", os.getenv("CLAUDE_ROUTER_PROXY", "(未设置)")),
            ("https_proxy", os.getenv("https_proxy", "(未设置)")),
            ("HTTPS_PROXY", os.getenv("HTTPS_PROXY", "(未设置)")),
            ("http_proxy", os.getenv("http_proxy", "(未设置)")),
            ("HTTP_PROXY", os.getenv("HTTP_PROXY", "(未设置)")),
        ]

        # Add to table
        for var_name, var_value in critical_vars:
            if var_value and var_value != "(未设置)":
                table.add_row(f"[bold]{var_name}[/bold]", f"[green]{var_value}[/green]")

        for var_name, var_value in auth_vars:
            if var_value and var_value != "(未设置)":
                table.add_row(var_name, f"[green]{var_value}[/green]")
            else:
                table.add_row(var_name, "[dim](未设置)[/dim]")

        table.add_row("", "")  # Separator
        for var_name, var_value in proxy_vars:
            if var_value and var_value != "(未设置)":
                table.add_row(var_name, f"[yellow]{var_value}[/yellow]")

        console.print(table)

        # Show active environment variables from config_service
        if env_snapshot:
            console.print("\n[bold cyan]当前生效的环境变量 (ConfigService 已设置):[/bold cyan]")
            active_table = Table(show_header=True, header_style="bold green")
            active_table.add_column("变量名", style="green")
            active_table.add_column("值", style="white")

            for key, value in sorted(env_snapshot.items()):
                if "TOKEN" in key or "KEY" in key:
                    value = self._mask_token(value)
                active_table.add_row(key, value)

            console.print(active_table)

        console.print()
        return True

    def _mask_token(self, token: Optional[str]) -> str:
        """Mask sensitive token for display.

        Args:
            token: Token to mask

        Returns:
            Masked token or "(未设置)"
        """
        if not token:
            return "(未设置)"
        if len(token) <= 10:
            return "***"
        return f"{token[:8]}...{token[-4:]}"

    async def _cmd_help(self, cmd: str) -> bool:
        """显示帮助命令"""
        help_text = """[bold]可用命令:[/bold]
  /q, /quit, /exit    退出CLI
  /new                开始新会话
  /sessions           显示会话历史
  /tenant <id>        设置租户ID
  /lang <language>    设置响应语言
  /skill <name>       设置Skill (默认: customer-service)
  /config             显示当前配置（包括工作目录）
  /env                显示环境变量（包括代理、token等）
  /help               显示此帮助

[bold]快捷键:[/bold]
  ESC                 中断当前 LLM 响应

[bold]默认配置:[/bold]
  Skill: customer-service (可访问知识库回答业务问题)
  租户ID: cli-debug
  语言: 中文"""
        console.print(Panel(help_text, title="帮助", border_style="blue"))
        console.print()
        return True
