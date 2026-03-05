"""
KDUBL XML Validator Module

A comprehensive XML validation module for KDUBL (Chinese E-Invoice UBL) documents.
Supports 8 document types with three-layer validation:
1. XML well-formedness
2. XSD schema validation
3. XSLT business rules validation (Schematron)

Supported document types:
- Invoice
- InvoiceResponse
- Order
- OrderBalance
- OrderCancellation
- OrderChange
- OrderOnly
- OrderResponse
"""

from .validator import KDUBLValidator
from .constants import DOCUMENT_TYPES, VALIDATION_RULES
from .report_generator import format_human_readable, format_error_summary

__version__ = "1.0.0"
__all__ = [
    'KDUBLValidator',
    'DOCUMENT_TYPES',
    'VALIDATION_RULES',
    'format_human_readable',
    'format_error_summary'
]
