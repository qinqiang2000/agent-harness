#!/usr/bin/env python
"""
AI Agent Service - Interactive CLI Debug Tool (Compatibility Layer)

This file maintains backward compatibility.
The actual implementation is in the cli/ package.

Usage:
    python cli.py
    python cli.py -s operational-analytics  # 指定skill
"""

from cli.main import main

if __name__ == "__main__":
    main()
