"""
Configuration Management for KDUBL Validator
"""

import os
from pathlib import Path

# Schema Base Path - 默认指向本包同级的 schemas/ 目录（相对路径，不依赖外部项目）
_DEFAULT_SCHEMA_BASE = str(Path(__file__).parent.parent.parent / 'schemas')

KDUBL_SCHEMA_BASE = os.environ.get('KDUBL_SCHEMA_PATH', _DEFAULT_SCHEMA_BASE)

# Validation Configuration
COLLECT_ALL_ERRORS = True  # Continue validation to collect all errors
MAX_ERRORS_REPORTED = 100  # Maximum number of errors to report
ENABLE_SCHEMA_CACHING = True  # Cache compiled schemas
MAX_XML_SIZE_MB = 10  # Maximum XML file size in MB

# Performance Settings
XSLT_CACHE_SIZE = 20  # Maximum number of XSLT stylesheets to cache
XSD_CACHE_SIZE = 20  # Maximum number of XSD schemas to cache


def validate_schema_path():
    """
    Validate that the schema directory exists.

    Raises:
        EnvironmentError: If the schema directory is not found
    """
    if not os.path.exists(KDUBL_SCHEMA_BASE):
        raise EnvironmentError(
            f"KDUBL schema directory not found: {KDUBL_SCHEMA_BASE}\n"
            f"Please set the KDUBL_SCHEMA_PATH environment variable to the correct path."
        )

    if not os.path.isdir(KDUBL_SCHEMA_BASE):
        raise EnvironmentError(
            f"KDUBL_SCHEMA_PATH is not a directory: {KDUBL_SCHEMA_BASE}"
        )


def get_schema_path(doc_type_config):
    """
    Get the absolute path to the XSD schema file for a document type.

    Args:
        doc_type_config: Document type configuration dictionary

    Returns:
        Absolute path to the XSD schema file
    """
    return os.path.join(KDUBL_SCHEMA_BASE, doc_type_config['xsd_path'])


def get_xslt_path(doc_type_config):
    """
    Get the absolute path to the XSLT validation file for a document type.

    Args:
        doc_type_config: Document type configuration dictionary

    Returns:
        Absolute path to the XSLT file
    """
    return os.path.join(KDUBL_SCHEMA_BASE, doc_type_config['xslt_path'])


def check_file_size(file_path):
    """
    Check if a file size is within the acceptable limit.

    Args:
        file_path: Path to the file

    Raises:
        ValueError: If file is too large
    """
    file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
    if file_size_mb > MAX_XML_SIZE_MB:
        raise ValueError(
            f"XML file is too large: {file_size_mb:.2f}MB (max: {MAX_XML_SIZE_MB}MB)"
        )
