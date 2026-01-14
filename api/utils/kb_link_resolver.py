"""KB 链接解析器 - 将 kb:// 协议链接转换为真实 URL."""

import logging
import re
from pathlib import Path
from typing import Optional

import yaml

logger = logging.getLogger(__name__)

# 知识库根目录（相对于项目根目录）
KB_BASE_PATH = Path("data/kb")


def resolve_kb_url(relative_path: str) -> Optional[str]:
    """从知识库文件的 YAML frontmatter 读取 URL.

    Args:
        relative_path: 相对于 data/kb/ 的文件路径

    Returns:
        文件 YAML frontmatter 中的 url 字段值，如果不存在则返回 None
    """
    file_path = KB_BASE_PATH / relative_path
    if not file_path.exists():
        logger.warning(f"[KB] File not found: {file_path}")
        return None

    try:
        content = file_path.read_text(encoding='utf-8')
        # 解析 YAML frontmatter
        if content.startswith('---'):
            end = content.find('---', 3)
            if end != -1:
                frontmatter = yaml.safe_load(content[3:end])
                if frontmatter and 'url' in frontmatter:
                    return frontmatter['url']
                logger.warning(f"[KB] No 'url' field in frontmatter: {file_path}")
        else:
            logger.warning(f"[KB] No YAML frontmatter found: {file_path}")
    except Exception as e:
        logger.error(f"[KB] Error reading file {file_path}: {e}")

    return None


def transform_kb_links(content: str) -> str:
    """将内容中的 kb:// 链接转换为真实 URL.

    将 [标题](kb://path/to/file.md) 格式的链接转换为 [标题](https://actual.url)

    Args:
        content: 包含 kb:// 链接的内容

    Returns:
        转换后的内容，kb:// 链接被替换为真实 URL
    """
    # 匹配 [任意标题](kb://路径) 格式
    pattern = r'\[([^\]]+)\]\(kb://([^)]+)\)'

    def replacer(match):
        title = match.group(1)
        path = match.group(2)
        url = resolve_kb_url(path)
        if url:
            logger.debug(f"[KB] Resolved: kb://{path} -> {url}")
            return f'[{title}]({url})'
        # 找不到 URL 时移除链接语法，只保留标题
        logger.warning(f"[KB] Could not resolve: kb://{path}, keeping title only")
        return title

    return re.sub(pattern, replacer, content)
