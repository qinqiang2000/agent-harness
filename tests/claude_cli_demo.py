#!/usr/bin/env python3
"""
Claude Code CLI 多轮对话 Demo

使用 CLI -p 模式实现多轮对话，支持自动保存 session_id
"""

import subprocess
import json
import sys
from typing import Optional, Dict, Any


class ClaudeCliChat:
    """Claude Code CLI 多轮对话管理器"""

    def __init__(
        self,
        allowed_tools: Optional[list] = None,
        skip_permissions: bool = True,
        cwd: Optional[str] = None,
        verbose: bool = False,
        stream: bool = True,
        proxy: Optional[str] = None
    ):
        """
        初始化聊天管理器

        Args:
            allowed_tools: 允许使用的工具列表，如 ["Read", "Grep", "Glob", "Bash"]
            skip_permissions: 是否跳过权限确认，默认开启
            cwd: 工作目录
            verbose: 是否显示详细日志（包括原始 JSON 响应）
            stream: 是否使用流式输出（实时显示），默认开启
            proxy: 代理地址，如 "http://127.0.0.1:7890"
        """
        self.session_id: Optional[str] = None
        self.allowed_tools = allowed_tools or ["Skill", "Read", "Grep", "Glob", "Bash", "WebFetch", "WebSearch"]
        self.skip_permissions = skip_permissions
        self.cwd = cwd
        self.verbose = verbose
        self.stream = stream
        self.proxy = proxy
        self.turn_count = 0

    def _build_command(self, prompt: str) -> list:
        """构建 claude CLI 命令"""
        # 根据 stream 模式选择输出格式
        output_format = "stream-json" if self.stream else "json"
        cmd = ["claude", "-p", prompt, "--output-format", output_format]

        # stream-json 需要 --verbose 标志
        if self.stream:
            cmd.append("--verbose")

        # 添加允许的工具
        if self.allowed_tools:
            cmd.extend(["--allowedTools", ",".join(self.allowed_tools)])

        # 跳过权限确认
        if self.skip_permissions:
            cmd.append("--dangerously-skip-permissions")

        # 如果有 session_id，使用 resume
        if self.session_id:
            cmd.extend(["--resume", self.session_id])

        return cmd

    def _get_env(self) -> Optional[Dict[str, str]]:
        """
        获取环境变量（包括代理设置）

        Returns:
            如果设置了 proxy，返回包含代理配置的环境变量字典
            如果未设置 proxy，返回 None（subprocess 会自动继承当前进程的环境变量）
        """
        if not self.proxy:
            # 返回 None 让 subprocess 自动继承当前 shell 的环境变量
            # 这样如果用户已经 export 了 http_proxy 等变量，会自动生效
            return None

        # 复制当前环境变量
        import os
        env = os.environ.copy()

        # 设置或覆盖代理配置
        env["https_proxy"] = self.proxy
        env["http_proxy"] = self.proxy
        env["all_proxy"] = self.proxy.replace("http://", "socks5://")

        return env

    def query_stream(self, prompt: str) -> Dict[str, Any]:
        """
        流式发送查询到 Claude Code CLI（实时输出）

        Args:
            prompt: 用户输入的问题

        Returns:
            解析后的最终结果
        """
        cmd = self._build_command(prompt)

        print(f"\n[执行命令] {' '.join(cmd)}")
        print("-" * 80)
        print("🔄 实时流式输出:\n")

        try:
            # 获取环境变量并添加 PYTHONUNBUFFERED 以强制无缓冲输出
            import os
            env = self._get_env()
            if env is None:
                env = os.environ.copy()
            env['PYTHONUNBUFFERED'] = '1'

            # 使用 Popen 实时读取输出
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd=self.cwd,
                env=env,
                bufsize=1  # 行缓冲
            )

            full_text = []
            final_result = {}
            session_created = False

            # 实时读取 stdout
            for line in process.stdout:
                if not line.strip():
                    continue

                try:
                    event = json.loads(line)

                    # 处理不同类型的事件
                    event_type = event.get("type", "")

                    if event_type == "session_created":
                        # 会话创建
                        session_id = event.get("session_id")
                        if session_id and not self.session_id:
                            self.session_id = session_id
                            print(f"\n✅ 会话已创建: {session_id[:8]}...\n")
                            session_created = True

                    elif event_type == "assistant_message":
                        # Claude 的文本回复
                        text = event.get("text", "")
                        if text:
                            print(text, end="", flush=True)
                            full_text.append(text)

                    elif event_type == "tool_use":
                        # 工具调用
                        tool_name = event.get("name", "")
                        if self.verbose:
                            print(f"\n\n[🔧 工具调用: {tool_name}]", flush=True)

                    elif event_type == "result":
                        # 最终结果
                        final_result = event
                        if not session_created and "session_id" in event:
                            self.session_id = event["session_id"]

                    elif event_type == "todos_update":
                        # 待办事项更新
                        if self.verbose:
                            todos = event.get("todos", [])
                            print(f"\n\n[📋 待办事项更新: {len(todos)} 项]", flush=True)

                    # Verbose 模式：显示所有事件
                    if self.verbose and event_type not in ["assistant_message"]:
                        print(f"\n[事件: {event_type}]", flush=True)

                except json.JSONDecodeError:
                    # 不是 JSON 行，可能是普通输出
                    if self.verbose:
                        print(line, end="", flush=True)

            # 等待进程结束
            return_code = process.wait(timeout=300)

            if return_code != 0:
                stderr_output = process.stderr.read()
                print(f"\n\n❌ 命令执行失败 (exit code: {return_code})")
                print(f"错误信息: {stderr_output}")
                return {
                    "error": stderr_output,
                    "exit_code": return_code
                }

            # 如果有最终结果，补充完整文本
            if final_result and full_text:
                final_result["result"] = "".join(full_text)

            return final_result if final_result else {
                "result": "".join(full_text),
                "session_id": self.session_id
            }

        except subprocess.TimeoutExpired:
            print("\n\n❌ 命令执行超时（超过5分钟）")
            process.kill()
            return {"error": "timeout"}
        except Exception as e:
            print(f"\n\n❌ 执行异常: {e}")
            return {"error": str(e)}

    def query(self, prompt: str) -> Dict[str, Any]:
        """
        发送查询到 Claude Code CLI

        Args:
            prompt: 用户输入的问题

        Returns:
            解析后的 JSON 响应
        """
        cmd = self._build_command(prompt)

        print(f"\n[执行命令] {' '.join(cmd)}")
        print("-" * 80)

        try:
            # 执行命令
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=self.cwd,
                env=self._get_env(),
                timeout=300  # 5分钟超时
            )

            if result.returncode != 0:
                print(f"❌ 命令执行失败 (exit code: {result.returncode})")
                print(f"错误信息: {result.stderr}")
                return {
                    "error": result.stderr,
                    "exit_code": result.returncode
                }

            # 解析 JSON 输出
            try:
                response = json.loads(result.stdout)

                # 提取 session_id（首次查询时）
                if not self.session_id and "session_id" in response:
                    self.session_id = response["session_id"]
                    print(f"✅ 会话已创建: {self.session_id}\n")

                return response

            except json.JSONDecodeError as e:
                print(f"❌ JSON 解析失败: {e}")
                print(f"原始输出:\n{result.stdout}")
                return {
                    "error": "JSON parse error",
                    "raw_output": result.stdout
                }

        except subprocess.TimeoutExpired:
            print("❌ 命令执行超时（超过5分钟）")
            return {"error": "timeout"}
        except Exception as e:
            print(f"❌ 执行异常: {e}")
            return {"error": str(e)}

    def _print_summary(self, response: Dict[str, Any]):
        """打印流式模式的汇总信息（不包括已经显示的文本内容）"""
        if "session_id" in response:
            session_short = response['session_id'][:8]
            print(f"📝 会话ID: {session_short}... (完整: {response['session_id']})")

        # 打印性能指标
        metrics = []
        if "duration_ms" in response:
            duration_sec = response["duration_ms"] / 1000
            metrics.append(f"⏱️  总耗时: {duration_sec:.2f}s")

        if "duration_api_ms" in response:
            api_duration_sec = response["duration_api_ms"] / 1000
            metrics.append(f"API耗时: {api_duration_sec:.2f}s")

        if "num_turns" in response:
            metrics.append(f"🔄 轮次: {response['num_turns']}")

        if metrics:
            print(" | ".join(metrics))

        # 打印成本信息
        if "total_cost_usd" in response:
            cost = response["total_cost_usd"]
            print(f"💰 成本: ${cost:.6f} USD")

        # 打印 Token 使用（简化版）
        if "usage" in response:
            usage = response["usage"]
            input_tokens = usage.get('input_tokens', 0)
            output_tokens = usage.get('output_tokens', 0)
            cache_read = usage.get('cache_read_input_tokens', 0)

            print(f"📊 Token: 输入 {input_tokens:,} | 输出 {output_tokens:,}", end="")
            if cache_read > 0:
                print(f" | 缓存读取 {cache_read:,}", end="")
            print()

        print("=" * 80)

    def print_response(self, response: Dict[str, Any]):
        """格式化打印响应"""
        # 如果是 verbose 模式，先打印原始 JSON
        if self.verbose:
            print("\n" + "=" * 80)
            print("🔍 原始 JSON 响应:")
            print("=" * 80)
            import json
            print(json.dumps(response, indent=2, ensure_ascii=False))
            print("=" * 80 + "\n")

        if "error" in response:
            print(f"\n❌ 错误: {response['error']}")
            if "raw_output" in response:
                print(f"\n原始输出:\n{response['raw_output'][:500]}...")
            return

        # 打印主要内容
        if "result" in response:
            print(f"\n🤖 Claude 回复:\n")
            print(response["result"])

        # 打印会话信息
        print("\n" + "-" * 80)

        if "session_id" in response:
            session_short = response['session_id'][:8]
            print(f"📝 会话ID: {session_short}... (完整: {response['session_id']})")

        # 打印性能指标
        metrics = []
        if "duration_ms" in response:
            duration_sec = response["duration_ms"] / 1000
            metrics.append(f"⏱️  总耗时: {duration_sec:.2f}s")

        if "duration_api_ms" in response:
            api_duration_sec = response["duration_api_ms"] / 1000
            metrics.append(f"API耗时: {api_duration_sec:.2f}s")

        if "num_turns" in response:
            metrics.append(f"🔄 轮次: {response['num_turns']}")

        if metrics:
            print(" | ".join(metrics))

        # 打印成本信息
        if "total_cost_usd" in response:
            cost = response["total_cost_usd"]
            print(f"💰 成本: ${cost:.6f} USD")

        # 打印 Token 使用（详细版）
        if "usage" in response:
            usage = response["usage"]
            input_tokens = usage.get('input_tokens', 0)
            output_tokens = usage.get('output_tokens', 0)
            cache_creation = usage.get('cache_creation_input_tokens', 0)
            cache_read = usage.get('cache_read_input_tokens', 0)

            # 计算实际的输入 token（包括缓存）
            total_input = input_tokens + cache_creation + cache_read
            total = total_input + output_tokens

            print(f"📊 Token 使用:")
            print(f"   • 输入: {input_tokens:,} tokens")
            print(f"   • 输出: {output_tokens:,} tokens")

            if cache_creation > 0 or cache_read > 0:
                print(f"   💾 缓存:")
                if cache_creation > 0:
                    print(f"      - 创建: {cache_creation:,} tokens")
                if cache_read > 0:
                    print(f"      - 读取: {cache_read:,} tokens (节省成本)")

            print(f"   🔢 总计: {total:,} tokens")

            # 服务端工具使用
            if "server_tool_use" in usage:
                tool_use = usage["server_tool_use"]
                web_search = tool_use.get("web_search_requests", 0)
                web_fetch = tool_use.get("web_fetch_requests", 0)
                if web_search > 0 or web_fetch > 0:
                    print(f"   🔧 工具调用:")
                    if web_search > 0:
                        print(f"      - Web Search: {web_search} 次")
                    if web_fetch > 0:
                        print(f"      - Web Fetch: {web_fetch} 次")

        # 打印模型使用详情（如果有多个模型）
        if "modelUsage" in response and len(response["modelUsage"]) > 0:
            print(f"\n📋 模型使用详情:")
            for model_name, model_stats in response["modelUsage"].items():
                model_short = model_name.replace("claude-", "")
                context_window = model_stats.get("contextWindow", 0)
                cost = model_stats.get("costUSD", 0)
                print(f"   • {model_short}")
                print(f"     - 上下文窗口: {context_window:,} tokens")
                print(f"     - 成本: ${cost:.6f} USD")

        # 打印权限拒绝（如果有）
        if "permission_denials" in response and response["permission_denials"]:
            print(f"\n⚠️  权限拒绝: {len(response['permission_denials'])} 项")
            for denial in response["permission_denials"]:
                print(f"   • {denial}")

        # 打印待办事项（如果有）
        if "todos" in response and response["todos"]:
            print("\n📋 待办事项:")
            for i, todo in enumerate(response["todos"], 1):
                status_icon = {
                    "pending": "⏳",
                    "in_progress": "🔄",
                    "completed": "✅"
                }.get(todo.get("status", "pending"), "❓")
                print(f"   {i}. {status_icon} {todo.get('content', 'N/A')}")

        # 打印错误状态
        if response.get("is_error"):
            print("\n⚠️  请求处理过程中发生错误")

        print("\n" + "=" * 80)

    def start_repl(self):
        """启动交互式 REPL"""
        print("=" * 80)
        print("Claude Code CLI 多轮对话 Demo")
        print("=" * 80)
        print(f"允许的工具: {', '.join(self.allowed_tools)}")
        print(f"跳过权限确认: {'是' if self.skip_permissions else '否'}")
        print(f"工作目录: {self.cwd or '当前目录'}")
        print(f"流式输出: {'是' if self.stream else '否'}")
        print(f"详细模式: {'是' if self.verbose else '否'}")
        if self.proxy:
            print(f"代理设置: {self.proxy}")
        print("\n命令:")
        print("  - 输入问题开始对话")
        print("  - 'exit' 或 'quit' 退出")
        print("  - 'reset' 重置会话（开始新对话）")
        print("  - 'session' 查看当前 session_id")
        print("=" * 80)

        while True:
            try:
                # 获取用户输入
                self.turn_count += 1
                user_input = input(f"\n[轮次 {self.turn_count}] 你: ").strip()

                if not user_input:
                    self.turn_count -= 1
                    continue

                # 处理特殊命令
                if user_input.lower() in ["exit", "quit"]:
                    print("\n👋 再见！")
                    break

                if user_input.lower() == "reset":
                    self.session_id = None
                    self.turn_count = 0
                    print("✅ 会话已重置，将开始新对话")
                    continue

                if user_input.lower() == "session":
                    if self.session_id:
                        print(f"当前 session_id: {self.session_id}")
                    else:
                        print("尚未创建会话")
                    self.turn_count -= 1
                    continue

                # 发送查询（根据模式选择）
                if self.stream:
                    response = self.query_stream(user_input)
                    # 流式模式下，响应已经实时打印，只显示汇总信息
                    if not response.get("error"):
                        print("\n" + "-" * 80)
                        self._print_summary(response)
                    else:
                        self.print_response(response)
                else:
                    response = self.query(user_input)
                    self.print_response(response)

            except KeyboardInterrupt:
                print("\n\n👋 检测到 Ctrl+C，退出...")
                break
            except Exception as e:
                print(f"\n❌ 发生错误: {e}")
                import traceback
                traceback.print_exc()


def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(
        description="Claude Code CLI 多轮对话 Demo",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例用法:
  # 基础使用（默认：流式输出 + 自动批准权限）
  python claude_cli_demo.py

  # 使用代理
  python claude_cli_demo.py --proxy http://127.0.0.1:7890

  # 指定工作目录
  python claude_cli_demo.py --cwd /path/to/project

  # 自定义允许的工具
  python claude_cli_demo.py --tools "Read,Grep,Bash"

  # 显示详细日志（包括原始 JSON 响应和事件）
  python claude_cli_demo.py --verbose

  # 使用批量模式（非流式）
  python claude_cli_demo.py --no-stream

  # 要求权限确认（禁用自动批准）
  python claude_cli_demo.py --no-skip-permissions

  # 组合使用
  python claude_cli_demo.py --proxy http://127.0.0.1:7890 --verbose
        """
    )

    parser.add_argument(
        "--tools",
        type=str,
        default="Skill, Read, Grep, Glob, Bash, WebFetch, WebSearch",
        help="允许使用的工具列表（逗号分隔），默认: Skill, Read, Grep, Glob, Bash, WebFetch, WebSearc"
    )

    parser.add_argument(
        "--cwd",
        type=str,
        default=None,
        help="工作目录路径"
    )

    parser.add_argument(
        "--verbose",
        action="store_true",
        help="显示详细日志，包括原始 JSON 响应"
    )

    parser.add_argument(
        "--no-stream",
        action="store_true",
        help="禁用流式输出（改用批量模式），默认启用流式"
    )

    parser.add_argument(
        "--no-skip-permissions",
        action="store_true",
        help="要求权限确认，默认自动批准所有工具使用"
    )

    parser.add_argument(
        "--proxy",
        type=str,
        default=None,
        help="代理地址，如 http://127.0.0.1:7890"
    )

    args = parser.parse_args()

    # 解析工具列表
    tools = [t.strip() for t in args.tools.split(",") if t.strip()]

    # 创建聊天实例
    chat = ClaudeCliChat(
        allowed_tools=tools,
        skip_permissions=not args.no_skip_permissions,  # 默认跳过权限
        cwd=args.cwd,
        verbose=args.verbose,
        stream=not args.no_stream,  # 默认开启流式
        proxy=args.proxy
    )

    # 启动 REPL
    chat.start_repl()


if __name__ == "__main__":
    main()
