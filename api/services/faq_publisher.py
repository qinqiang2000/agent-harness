"""Generate FAQ markdown content from approved DB entries."""
import logging
from pathlib import Path

from api.constants import AGENT_CWD
from api.db import get_faq_pool

logger = logging.getLogger(__name__)

KB_DIR = AGENT_CWD / ".claude" / "skills" / "issue-diagnosis" / "kb"

FAQ_CATEGORIES = [
    "开票", "收票", "鉴权登录", "接口参数", "进项发票采集", "性能超时", "faq-newtimeai-invoice"
]

CATEGORY_HEADERS = {
    "开票": "# 开票类 FAQ\n\n> 涵盖：发票开具失败、开票报错、票种问题、开票状态异常、权益配置等。",
    "收票": "# 收票类 FAQ\n\n> 涵盖：发票查验失败、影像识别异常、收票状态异常、PDF/OFD 下载问题等。",
    "鉴权登录": "# 鉴权登录类 FAQ\n\n> 涵盖：登录失败、token 失效、权限不足、clientId 异常、二维码/验证码问题等。",
    "接口参数": "# 接口参数类 FAQ\n\n> 涵盖：参数校验失败、字段格式错误、必填项缺失、报文格式不合规等。",
    "进项发票采集": "# 进项发票采集类 FAQ\n\n> 涵盖：全量发票查询、发票表头、抵扣勾选、退税勾选、入账、版式文件下载、海关缴款书下载等。\n> 涉及服务：api-elc-digital-invoice、api-elc-invoice-lqpt",
    "性能超时": "# 性能超时类 FAQ\n\n> 涵盖：接口超时、服务响应慢、连接失败、限流等。",
    "faq-newtimeai-invoice": "# 新时代开票接口异常 FAQ\n\n> 适用场景：日志中出现 `newtimeai`、`blueTicket`、`fullExteriorInvoke`、`open.gateway.newtimeai.com`、`局端` 等关键词时参考本文件。\n> 错误码来源：**新时代网关**（非发票云内部错误码）。",
}


def _faq_filename(category: str) -> str:
    if category == "faq-newtimeai-invoice":
        return "faq-newtimeai-invoice.md"
    return f"{category}-faq.md"


async def generate_category_content(category: str) -> str:
    """Generate markdown content for one category from approved DB entries."""
    pool = await get_faq_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT * FROM faq_items
               WHERE category=$1 AND status='approved'
               ORDER BY sort_order ASC, id ASC""",
            category
        )

    header = CATEGORY_HEADERS.get(category, f"# {category} FAQ")
    lines = [header, "\n\n---\n"]

    qa_counter = 0
    for row in rows:
        if row["type"] == "section":
            lines.append(f"\n## {row['question']}\n\n{row['answer']}\n\n---\n")
        else:
            qa_counter += 1
            lines.append(f"\n## Q{qa_counter}: {row['question']}\n\n{row['answer']}\n\n---\n")

    # 保留原文件末尾的固定 section（如"新时代通道日志分析"）
    faq_file = KB_DIR / _faq_filename(category)
    if faq_file.exists():
        original = faq_file.read_text(encoding="utf-8")
        marker = "\n## 新时代通道日志分析"
        if marker in original:
            lines.append(original[original.index(marker):])

    return "".join(lines)


async def generate_all_contents() -> dict[str, str]:
    """Generate markdown content for all categories. Returns {category: content}."""
    result = {}
    for category in FAQ_CATEGORIES:
        result[category] = await generate_category_content(category)
    return result
