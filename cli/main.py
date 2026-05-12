#!/usr/bin/env python
"""
AI Agent Service - Interactive CLI Debug Tool

Usage:
    python -m cli.main
    或
    python cli/main.py
    python cli/main.py -s operational-analytics  # 指定skill
"""

import argparse
import asyncio
import logging
import sys
from pathlib import Path

from dotenv import load_dotenv

# Load environment variables FIRST (before importing project modules)
load_dotenv('.env')

from cli.repl import REPLRunner

# Configure logging
log_dir = Path(__file__).parent.parent / "log"
log_dir.mkdir(exist_ok=True)

# 配置根logger
root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)

# 文件handler - 记录所有INFO及以上级别的日志
file_handler = logging.FileHandler(
    log_dir / "cli.log",
    encoding='utf-8'
)
file_handler.setLevel(logging.INFO)
file_formatter = logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
file_handler.setFormatter(file_formatter)

# 控制台handler - 只显示WARNING及以上级别（避免INFO日志污染CLI输出）
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.WARNING)
console_formatter = logging.Formatter('%(levelname)s: %(message)s')
console_handler.setFormatter(console_formatter)

# 添加handlers
root_logger.addHandler(file_handler)
root_logger.addHandler(console_handler)


def parse_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        description='AI Agent Service - Interactive CLI Debug Tool',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        '-s', '--skill',
        type=str,
        default='customer-service',
        help='指定要使用的skill名称 (默认: customer-service)'
    )
    return parser.parse_args()


def main():
    """主函数"""
    try:
        args = parse_args()
        repl = REPLRunner(skill=args.skill)
        asyncio.run(repl.run())
    except KeyboardInterrupt:
        print("\n\033[33minterrupted\033[0m")
        sys.exit(0)


if __name__ == "__main__":
    main()
