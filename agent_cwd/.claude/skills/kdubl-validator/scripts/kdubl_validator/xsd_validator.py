"""
XSD Schema Validation
"""

import os
from lxml import etree
from .config import get_schema_path, ENABLE_SCHEMA_CACHING, XSD_CACHE_SIZE


class XSDValidator:
    """XSD Schema validator with caching support."""

    def __init__(self):
        """Initialize the XSD validator."""
        self._schema_cache = {}

    def load_schema(self, doc_type, doc_type_config):
        """
        Load and compile an XSD schema.

        Args:
            doc_type: Document type name
            doc_type_config: Document type configuration dictionary

        Returns:
            lxml.etree.XMLSchema: Compiled schema object

        Raises:
            FileNotFoundError: If schema file is not found
            etree.XMLSchemaParseError: If schema is invalid
        """
        # Check cache
        if ENABLE_SCHEMA_CACHING and doc_type in self._schema_cache:
            return self._schema_cache[doc_type]

        # Get schema file path
        schema_path = get_schema_path(doc_type_config)

        if not os.path.exists(schema_path):
            raise FileNotFoundError(f"XSD schema 文件不存在: {schema_path}")

        try:
            # Parse schema with proper base path for relative imports
            schema_dir = os.path.dirname(schema_path)
            parser = etree.XMLParser(resolve_entities=False)

            # Change to schema directory to resolve relative imports
            original_dir = os.getcwd()
            try:
                os.chdir(schema_dir)
                xsd_doc = etree.parse(schema_path, parser)
                schema = etree.XMLSchema(xsd_doc)
            finally:
                os.chdir(original_dir)

            # Cache the schema
            if ENABLE_SCHEMA_CACHING:
                if len(self._schema_cache) >= XSD_CACHE_SIZE:
                    # Remove oldest entry
                    self._schema_cache.pop(next(iter(self._schema_cache)))
                self._schema_cache[doc_type] = schema

            return schema

        except etree.XMLSchemaParseError as e:
            raise etree.XMLSchemaParseError(f"XSD schema 解析错误: {str(e)}")
        except Exception as e:
            raise Exception(f"加载 XSD schema 时出错: {str(e)}")

    def validate(self, xml_tree, doc_type, doc_type_config):
        """
        Validate an XML tree against its XSD schema.

        Args:
            xml_tree: Parsed XML tree
            doc_type: Document type name
            doc_type_config: Document type configuration

        Returns:
            list: List of validation error dictionaries
        """
        errors = []

        try:
            # Load schema
            schema = self.load_schema(doc_type, doc_type_config)

            # Validate
            is_valid = schema.validate(xml_tree)

            # Collect errors
            if not is_valid:
                for error in schema.error_log:
                    errors.append({
                        'stage': 'xsd',
                        'severity': 'error',
                        'message': error.message,
                        'line': error.line,
                        'column': error.column,
                        'location': error.path if error.path else 'unknown'
                    })

        except FileNotFoundError as e:
            errors.append({
                'stage': 'xsd',
                'severity': 'fatal',
                'message': str(e),
                'line': None,
                'location': 'schema'
            })
        except Exception as e:
            errors.append({
                'stage': 'xsd',
                'severity': 'fatal',
                'message': f"XSD 验证失败: {str(e)}",
                'line': None,
                'location': 'unknown'
            })

        return errors

    def clear_cache(self):
        """Clear the schema cache."""
        self._schema_cache.clear()
