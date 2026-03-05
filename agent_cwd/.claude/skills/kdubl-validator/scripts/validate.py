#!/usr/bin/env python3
"""
KDUBL XML 本地校验脚本

用法:
  # 校验 XML 文件
  python validate.py --file /path/to/invoice.xml

  # 校验 XML 内容字符串（通过 stdin）
  echo '<Invoice>...</Invoice>' | python validate.py --stdin

  # 列出支持的文档类型
  python validate.py --list-types

输出：JSON 格式校验报告，包含 valid/errors/summary 等字段。
"""

import sys
import json
import argparse
from pathlib import Path

# 将脚本所在目录加入 path，使 kdubl_validator 包可以被直接 import
sys.path.insert(0, str(Path(__file__).parent))

from kdubl_validator import KDUBLValidator
from kdubl_validator.constants import DOCUMENT_TYPES, VALIDATION_RULES
from kdubl_validator.report_generator import format_human_readable


def validate_file(path: str) -> dict:
    v = KDUBLValidator()
    report = v.validate(path, input_type='path')
    return report


def validate_content(xml_content: str) -> dict:
    v = KDUBLValidator()
    report = v.validate(xml_content, input_type='content')
    return report


def list_types() -> list:
    return [
        {
            "name": name,
            "root_element": cfg["root_element"],
            "namespace": cfg["namespace"],
            "ubl_version": cfg["ubl_version"],
        }
        for name, cfg in DOCUMENT_TYPES.items()
    ]


def main():
    parser = argparse.ArgumentParser(description='KDUBL XML 本地校验工具')
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--file', metavar='PATH', help='校验指定 XML 文件')
    group.add_argument('--stdin', action='store_true', help='从 stdin 读取 XML 内容')
    group.add_argument('--list-types', action='store_true', help='列出支持的文档类型')
    parser.add_argument('--human', action='store_true', help='同时输出人类可读报告')
    args = parser.parse_args()

    if args.list_types:
        print(json.dumps(list_types(), ensure_ascii=False, indent=2))
        return

    try:
        if args.file:
            report = validate_file(args.file)
        else:
            xml_content = sys.stdin.read()
            report = validate_content(xml_content)

        if args.human:
            print(format_human_readable(report))
            print()

        # 输出 JSON 结构（供 Agent 解析）
        print(json.dumps(report, ensure_ascii=False, indent=2))

    except FileNotFoundError as e:
        print(json.dumps({"error": f"文件不存在: {e}"}, ensure_ascii=False))
        sys.exit(1)
    except Exception as e:
        print(json.dumps({"error": str(e)}, ensure_ascii=False))
        sys.exit(1)


if __name__ == '__main__':
    main()
