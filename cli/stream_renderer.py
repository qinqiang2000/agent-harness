"""Stream output renderer."""


class StreamRenderer:
    """简单的输出渲染器"""

    def start_response(self):
        """开始响应"""
        print("💡 按 ESC 键可中断响应")

    def print_text(self, text: str):
        """打印文本

        Args:
            text: 要打印的文本
        """
        if text:
            print(text)

    def on_session_created(self, session_id: str):
        """会话创建回调

        Args:
            session_id: 新创建的会话 ID
        """
        print(f"✓ 会话已创建: {session_id[:16]}...")

    def on_result(self, result: dict):
        """完成回调

        Args:
            result: 结果字典
        """
        duration = result.get("duration_ms", 0) / 1000
        print(f"✓ 完成 ({duration:.1f}s)\n")

    def show_error(self, error: dict):
        """显示错误

        Args:
            error: 错误字典
        """
        print(f"✗ 错误: {error.get('message')}\n")

    def show_interrupted(self):
        """显示中断消息"""
        print("⚠ 响应已中断\n")
