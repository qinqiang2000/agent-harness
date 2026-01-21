"""KB 链接解析器 - 将 kb:// 协议链接转换为真实 URL."""

import logging
import re
from pathlib import Path
from typing import Optional

import yaml

from api.constants import DATA_DIR

logger = logging.getLogger(__name__)

# 知识库根目录
KB_BASE_PATH = DATA_DIR / "kb"


def resolve_kb_url(relative_path: str) -> Optional[str]:
    """从知识库文件的 YAML frontmatter 读取 URL.

    Args:
        relative_path: 相对于 data/kb/ 的文件路径

    Returns:
        文件 YAML frontmatter 中的 url 字段值，如果不存在则返回 None
    """
    from api.utils.filename_normalizer import normalize_filename

    file_path = KB_BASE_PATH / relative_path
    if not file_path.exists():
        # 尝试规范化路径（处理全角半角括号等）
        normalized_path = normalize_filename(relative_path)
        if normalized_path != relative_path:
            file_path = KB_BASE_PATH / normalized_path
            if file_path.exists():
                logger.debug(f"[KB] File found after normalization: {relative_path} -> {normalized_path}")
            else:
                logger.warning(f"[KB] File not found: {file_path} (tried normalized)")
                return None
        else:
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


def transform_kb_links(content: str, filename_to_path: dict[str, str] = None) -> str:
    """基于文件名匹配，将 kb:// 链接转换为真实 URL.

    将 [标题](kb://任意路径/文件名.md) 格式的链接转换为 [标题](https://actual.url)
    通过 filename_to_path 映射（从 Read 工具追踪）找到正确的文件路径。

    Args:
        content: 包含 kb:// 链接的内容
        filename_to_path: {文件名: 完整路径} 映射，从 Read 工具调用追踪得到

    Returns:
        转换后的内容，kb:// 链接被替换为真实 URL
    """
    filename_to_path = filename_to_path or {}

    # 匹配 [任意标题](kb://路径.md) 格式
    # 使用 .+?\.md 非贪婪匹配，确保能处理路径中包含括号的情况
    pattern = r'\[([^\]]+)\]\(kb://(.+?\.md)\)'

    def replacer(match):
        from api.utils.filename_normalizer import normalize_filename

        title = match.group(1)
        kb_path = match.group(2)
        filename = Path(kb_path).name

        # 优先级1：精确匹配原始文件名
        if filename in filename_to_path:
            correct_path = filename_to_path[filename]
            url = resolve_kb_url(correct_path)
            if url:
                logger.info(f"[KB] Resolved (exact): {filename} -> {url}")
                return f'[{title}]({url})'

        # 优先级2：规范化匹配（容错 LLM 全角/半角不一致）
        normalized = normalize_filename(filename)
        if normalized != filename and normalized in filename_to_path:
            correct_path = filename_to_path[normalized]
            url = resolve_kb_url(correct_path)
            if url:
                logger.info(f"[KB] Resolved (normalized): {filename} -> {normalized} -> {url}")
                return f'[{title}]({url})'

        # 优先级3：尝试直接解析原路径（兼容旧逻辑）
        url = resolve_kb_url(kb_path)
        if url:
            logger.debug(f"[KB] Resolved directly: kb://{kb_path} -> {url}")
            return f'[{title}]({url})'

        # 优先级4：模糊匹配 - 从已读文件中找字符串相似度最高的
        if filename_to_path:
            from difflib import SequenceMatcher

            normalized_kb_path = normalize_filename(kb_path)
            best_match, best_score = max(
                ((path, SequenceMatcher(None, normalized_kb_path, normalize_filename(path)).ratio())
                 for path in filename_to_path.values()),
                key=lambda x: x[1],
                default=(None, 0)
            )

            if best_match and best_score > 0.5:
                url = resolve_kb_url(best_match)
                if url:
                    logger.info(f"[KB] Resolved (fuzzy): {kb_path} -> {best_match} (score={best_score:.2f}) -> {url}")
                    return f'[{title}]({url})'

        # 都失败，只保留标题
        logger.warning(f"[KB] Not found: {filename} (normalized: {normalized})")
        return title

    return re.sub(pattern, replacer, content)
