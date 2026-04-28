"""Output redaction for external-facing responses."""

import re
from typing import Optional

# (pattern, replacement) — order matters: credentials first, then PII
_RULES: list[tuple[re.Pattern, str]] = [
    # credentials
    (re.compile(r'(?i)(clientSecret|entryKey|appSecret|privateKey|password|token|secret)\s*[:=]\s*\S+'), r'\1=***'),
    # phone: 11-digit starting with 1
    (re.compile(r'\b(1[3-9]\d)\d{4}(\d{4})\b'), r'\1****\2'),
    # ID card: 18-digit (last char may be X)
    (re.compile(r'\b(\d{6})\d{8}(\d{3}[\dX])\b'), r'\1********\2'),
    # tax number: 15/18/20 digits (unified social credit code pattern)
    (re.compile(r'\b([A-Z0-9]{4})[A-Z0-9]{9,14}([A-Z0-9]{2})\b'), r'\1******\2'),
    # invoice number: 8 digits standalone
    (re.compile(r'(?<!\d)(\d{8})(?!\d)'), r'********'),
    # invoice code: 10 or 12 digits standalone
    (re.compile(r'(?<!\d)(\d{10}|\d{12})(?!\d)'), r'************'),
]


def redact(text: str) -> str:
    for pattern, replacement in _RULES:
        text = pattern.sub(replacement, text)
    return text


def should_redact(skill: Optional[str], tenant_id: Optional[str] = None) -> bool:
    return skill == "issue-diagnosis-external" or tenant_id == "open_api"
