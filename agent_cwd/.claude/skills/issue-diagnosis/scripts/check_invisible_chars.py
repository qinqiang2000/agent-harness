#!/usr/bin/env python3
"""
不可见字符检测工具
对应逻辑来自"不可见字符.html"

检测文本中的不可见/控制类 Unicode 字符（排除换行 \\n 和制表符 \\t）。

用法：
  python3 check_invisible_chars.py '文本内容'
  python3 check_invisible_chars.py --file /path/to/file.txt
  echo '文本' | python3 check_invisible_chars.py
  python3 check_invisible_chars.py --json '{"field": "值"}'  # 检查 JSON 字符串中所有字段值
"""

import sys
import json
import argparse
import unicodedata


# 对应 HTML 中 \p{Cc}\p{Cf}\p{Cn}\p{Co}\p{Cs} 类别
INVISIBLE_CATEGORIES = {'Cc', 'Cf', 'Cn', 'Co', 'Cs'}
EXCLUDE_CODEPOINTS = {0x000A, 0x0009}  # 换行、制表符


def find_invisible(text, label=""):
    """返回文本中所有不可见字符的列表，每项为 (位置, 字符, unicode码点)"""
    found = []
    for i, ch in enumerate(text):
        cp = ord(ch)
        if cp in EXCLUDE_CODEPOINTS:
            continue
        cat = unicodedata.category(ch)
        if cat in INVISIBLE_CATEGORIES:
            found.append((i, ch, cp, cat))
    return found


def report(found, label=""):
    if not found:
        if label:
            print(f"✅ [{label}] 未发现不可见字符")
        else:
            print("✅ 未发现不可见字符")
        return False

    prefix = f"[{label}] " if label else ""
    print(f"❌ {prefix}发现 {len(found)} 个不可见字符：")
    for pos, ch, cp, cat in found:
        print(f"  位置 {pos}: \\u{cp:04X}  类别={cat}  上下文=...{repr(ch)}...")
    return True


def check_text(text, label=""):
    found = find_invisible(text, label)
    return report(found, label)


def check_json_values(data, path=""):
    """递归检查 JSON 中所有字符串值"""
    has_error = False
    if isinstance(data, str):
        found = find_invisible(data)
        if found:
            report(found, label=path or "root")
            has_error = True
    elif isinstance(data, dict):
        for k, v in data.items():
            cur_path = f"{path}.{k}" if path else k
            if check_json_values(v, cur_path):
                has_error = True
    elif isinstance(data, list):
        for i, v in enumerate(data):
            cur_path = f"{path}[{i}]"
            if check_json_values(v, cur_path):
                has_error = True
    return has_error


def main():
    parser = argparse.ArgumentParser(description="不可见字符检测工具")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--file", help="文本文件路径")
    group.add_argument("--json", help="JSON 字符串，递归检查所有字段值")
    parser.add_argument("text_positional", nargs="?", help="直接传入文本（位置参数）")
    args = parser.parse_args()

    if args.file:
        with open(args.file, "r", encoding="utf-8") as f:
            text = f.read()
        check_text(text)
    elif args.json:
        try:
            data = json.loads(args.json)
        except json.JSONDecodeError as e:
            print(f"JSON 解析失败：{e}")
            sys.exit(1)
        has_error = check_json_values(data)
        if not has_error:
            print("✅ 所有字段值中未发现不可见字符")
    elif args.text_positional:
        check_text(args.text_positional)
    else:
        text = sys.stdin.read()
        check_text(text)


if __name__ == "__main__":
    main()
