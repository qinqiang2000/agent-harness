"""
交互日志记录器 - 记录生产环境的 AI 交互数据

日志写入 log/interactions.log，按天滚动（归档为 interactions.log.YYYYMMDD）。
每行一条 JSON，供 detect_bad_cases.py 离线消费。
"""

import json
import logging
from datetime import datetime
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
LOG_DIR = PROJECT_ROOT / "log"
LOG_DIR.mkdir(parents=True, exist_ok=True)

FALLBACK_PHRASE = "抱歉,在发票云知识库没找到本答案"

# 专用 logger，只输出纯 JSON 行，不加 logging 时间前缀
_interactions_logger = logging.getLogger("interactions")
_interactions_logger.setLevel(logging.INFO)
_interactions_logger.propagate = False  # 不传播到 root logger

_handler = TimedRotatingFileHandler(
    filename=str(LOG_DIR / "interactions.log"),
    when="midnight",
    backupCount=30,
    encoding="utf-8",
)
_handler.setFormatter(logging.Formatter("%(message)s"))
_interactions_logger.addHandler(_handler)


class InteractionLogger:
    """交互日志记录器（单例使用）"""

    async def log(self, interaction: dict):
        """记录一条交互，自动注入 timestamp。"""
        interaction.setdefault("timestamp", datetime.now().isoformat())
        try:
            _interactions_logger.info(json.dumps(interaction, ensure_ascii=False))
        except Exception as e:
            logging.getLogger(__name__).warning(f"InteractionLogger log failed: {e}")


# 单例
interaction_logger = InteractionLogger()
