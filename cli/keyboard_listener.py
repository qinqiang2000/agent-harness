"""Non-blocking keyboard listener."""

import select
import sys
import termios
import tty


class KeyboardListener:
    """非阻塞键盘监听器

    用于在流式输出期间检测 ESC 键按下。
    """

    def __init__(self):
        """初始化键盘监听器

        自动设置终端为 cbreak 模式以捕获键盘输入。
        """
        self.fd = sys.stdin.fileno()
        self.old_settings = termios.tcgetattr(self.fd)
        # Set cbreak mode immediately to prevent ESC key from echoing
        tty.setcbreak(self.fd)

    def check_esc(self) -> bool:
        """检查是否按下 ESC 键（非阻塞）

        Returns:
            如果检测到 ESC 键返回 True，否则返回 False
        """
        try:
            rlist, _, _ = select.select([sys.stdin], [], [], 0)
            if rlist:
                char = sys.stdin.read(1)
                return ord(char) == 27  # ESC key
        except Exception:
            pass
        return False

    def restore(self):
        """恢复终端设置

        在完成键盘监听后必须调用此方法恢复终端状态。
        """
        try:
            termios.tcsetattr(self.fd, termios.TCSADRAIN, self.old_settings)
        except Exception:
            pass
