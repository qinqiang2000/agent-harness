"""Image processing utilities for knowledge base."""

import re
from typing import List, Tuple


def parse_markdown_images(text: str) -> List[str]:
    """从 markdown 文本中提取图片路径

    Args:
        text: markdown 文本内容

    Returns:
        图片路径列表（相对路径或 URL）
    """
    # 匹配 ![alt](path) 格式
    pattern = r'!\[.*?\]\(([^)]+\.(?:png|jpg|jpeg|gif|webp))\)'
    return re.findall(pattern, text, re.IGNORECASE)


def convert_relative_to_url(relative_path: str, base_url: str) -> str:
    """将相对路径转换为完整 URL

    Args:
        relative_path: 如 ../../../../assets/abc/1234.png
        base_url: 如 http://host:9090

    Returns:
        完整 URL，如 http://host:9090/kb/assets/abc/1234.png
    """
    # 提取 assets/xxx/yyy.png 部分
    match = re.search(r'assets/([^/]+/[^)\s]+)', relative_path)
    if match:
        return f"{base_url}/kb/assets/{match.group(1)}"
    return None


def extract_images_from_content(content: str, base_url: str) -> Tuple[str, List[str]]:
    """从内容中提取图片 URL，并返回清理后的文本

    Args:
        content: 包含 markdown 图片的文本
        base_url: 服务基础 URL

    Returns:
        (cleaned_content, image_urls) 元组
    """
    relative_paths = parse_markdown_images(content)
    image_urls = []

    for path in relative_paths:
        # 如果已经是完整 URL，直接使用
        if path.startswith(('http://', 'https://')):
            image_urls.append(path)
        else:
            # 转换相对路径为 URL
            url = convert_relative_to_url(path, base_url)
            if url:
                image_urls.append(url)

    # 移除 markdown 图片语法，保留文本内容
    cleaned = re.sub(r'!\[.*?\]\([^)]+\)', '', content)
    # 清理多余空行
    cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)

    return cleaned.strip(), image_urls
