#!/usr/bin/env python3
"""KB 链接生成工具 - 将 KB 文件路径转换为 markdown 链接

Usage:
    # 支持多种路径格式，脚本自动处理
    python kb_link.py "data/kb/产品与交付知识/.../文档.md"
    python kb_link.py "./data/kb/产品与交付知识/.../文档.md"
    python kb_link.py "产品与交付知识/.../文档.md"

    # 批量处理多个文件
    python kb_link.py "path1.md" "path2.md" "path3.md"

Output:
    [文档标题](https://actual.url)

    # 批量输出（每行一个）
    [文档1](https://url1)
    [文档2](https://url2)
"""
import sys
from pathlib import Path
import yaml

# KB 根目录（相对于 agent_cwd）
KB_BASE = Path(__file__).parent.parent.parent.parent.parent / "data" / "kb"

def normalize_path(path: str) -> str:
    """标准化路径，自动去除各种前缀"""
    prefixes = [
        "./data/kb/",
        "data/kb/",
        "/data/kb/",
    ]
    for prefix in prefixes:
        if path.startswith(prefix):
            return path[len(prefix):]
    return path

def get_kb_link(input_path: str) -> str:
    """读取 KB 文件的 frontmatter，返回 [title](url) 格式的链接

    Best Practice: "Solve, don't punt" - 处理所有错误情况，返回有意义的结果
    """
    relative_path = normalize_path(input_path)
    file_path = KB_BASE / relative_path

    # 错误处理：文件不存在时，返回文件名作为纯文本（不让 Claude 再处理）
    if not file_path.exists():
        filename = Path(input_path).stem
        print(f"⚠️ 文件不存在，返回纯文本: {input_path}", file=sys.stderr)
        return filename

    try:
        content = file_path.read_text(encoding='utf-8')

        # 获取文件名作为默认标题
        default_title = Path(relative_path).stem

        # 尝试解析 YAML frontmatter
        if content.startswith('---'):
            end = content.find('---', 3)
            if end != -1:
                try:
                    frontmatter = yaml.safe_load(content[3:end])
                    if frontmatter:
                        title = frontmatter.get('title', default_title)
                        url = frontmatter.get('url')
                        if url:
                            return f"[{title}]({url})"
                        # 有 frontmatter 但没有 url，返回带标题的纯文本
                        print(f"⚠️ 文件缺少 url 字段: {input_path}", file=sys.stderr)
                        return title
                except yaml.YAMLError:
                    pass

        # 无有效 frontmatter，返回文件名
        print(f"⚠️ 文件缺少有效的 YAML frontmatter: {input_path}", file=sys.stderr)
        return default_title

    except Exception as e:
        print(f"⚠️ 读取文件失败 ({e}): {input_path}", file=sys.stderr)
        return Path(input_path).stem

def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(0)

    if sys.argv[1] in ['-h', '--help']:
        print(__doc__)
        sys.exit(0)

    # 支持批量处理：输出每个路径对应的链接
    for input_path in sys.argv[1:]:
        print(get_kb_link(input_path))

if __name__ == '__main__':
    main()
