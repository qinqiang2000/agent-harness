"""
XSLT Business Rules Validation and SVRL Parsing

Uses Saxon-HE (saxonche) for XSLT 2.0/3.0 support with fallback to lxml for XSLT 1.0.
"""

import os
import tempfile
from lxml import etree
from .config import get_xslt_path, ENABLE_SCHEMA_CACHING, XSLT_CACHE_SIZE
from .constants import SVRL_NAMESPACE

# Try to import Saxon for XSLT 2.0/3.0 support
try:
    from saxonche import PySaxonProcessor
    SAXON_AVAILABLE = True
except ImportError:
    SAXON_AVAILABLE = False


class XSLTValidator:
    """XSLT validator with Schematron SVRL output parsing.

    Uses Saxon-HE for XSLT 2.0+ support when available, falls back to lxml for XSLT 1.0.
    """

    def __init__(self):
        """Initialize the XSLT validator."""
        self._xslt_cache = {}
        self._saxon_processor = None

        if SAXON_AVAILABLE:
            self._saxon_processor = PySaxonProcessor(license=False)

    def load_xslt_lxml(self, doc_type, xslt_path):
        """
        Load and compile an XSLT stylesheet using lxml (XSLT 1.0 only).

        Args:
            doc_type: Document type name
            xslt_path: Path to XSLT file

        Returns:
            lxml.etree.XSLT: Compiled XSLT transform
        """
        # Check cache
        if ENABLE_SCHEMA_CACHING and doc_type in self._xslt_cache:
            return self._xslt_cache[doc_type]

        parser = etree.XMLParser(resolve_entities=False)

        # Change to XSLT directory to resolve relative imports
        xslt_dir = os.path.dirname(xslt_path)
        original_dir = os.getcwd()
        try:
            os.chdir(xslt_dir)
            xslt_doc = etree.parse(xslt_path, parser)
            transform = etree.XSLT(xslt_doc)
        finally:
            os.chdir(original_dir)

        # Cache the transform
        if ENABLE_SCHEMA_CACHING:
            if len(self._xslt_cache) >= XSLT_CACHE_SIZE:
                # Remove oldest entry
                self._xslt_cache.pop(next(iter(self._xslt_cache)))
            self._xslt_cache[doc_type] = transform

        return transform

    def validate(self, xml_tree, doc_type, doc_type_config):
        """
        Validate an XML tree using XSLT transformation and parse SVRL output.

        Args:
            xml_tree: Parsed XML tree
            doc_type: Document type name
            doc_type_config: Document type configuration

        Returns:
            list: List of validation error dictionaries
        """
        errors = []

        try:
            # Get XSLT file path
            xslt_path = get_xslt_path(doc_type_config)

            if not os.path.exists(xslt_path):
                raise FileNotFoundError(f"XSLT 验证文件不存在: {xslt_path}")

            # Use Saxon if available (for XSLT 2.0/3.0), otherwise use lxml
            if SAXON_AVAILABLE:
                svrl_result_str = self._validate_with_saxon(xml_tree, doc_type, xslt_path)
                # Parse the result as XML
                svrl_result = etree.fromstring(svrl_result_str.encode('utf-8'))
            else:
                transform = self.load_xslt_lxml(doc_type, xslt_path)
                svrl_result = transform(xml_tree)

            # Parse SVRL output
            errors = self.parse_svrl_output(svrl_result)

        except FileNotFoundError as e:
            errors.append({
                'stage': 'xslt',
                'severity': 'fatal',
                'message': str(e),
                'line': None,
                'location': 'xslt'
            })
        except Exception as e:
            errors.append({
                'stage': 'xslt',
                'severity': 'fatal',
                'message': f"XSLT 验证失败: {str(e)}",
                'line': None,
                'location': 'unknown'
            })

        return errors

    def _validate_with_saxon(self, xml_tree, doc_type, xslt_path):
        """
        Validate using Saxon processor.

        Args:
            xml_tree: Parsed XML tree
            doc_type: Document type name
            xslt_path: Path to XSLT file

        Returns:
            str: SVRL result as string
        """
        # Create a fresh XSLT processor
        xslt_processor = self._saxon_processor.new_xslt30_processor()

        # Get absolute paths
        abs_xslt_path = os.path.abspath(xslt_path)
        xslt_dir = os.path.dirname(abs_xslt_path)

        # Set working directory for resolving imports
        xslt_processor.set_cwd(xslt_dir)

        # Convert lxml tree to string
        xml_string = etree.tostring(xml_tree, encoding='unicode')

        # Write XML to a temporary file (Saxon's file-based API is most reliable)
        with tempfile.NamedTemporaryFile(mode='w', suffix='.xml', delete=False, encoding='utf-8') as tmp_in:
            tmp_in.write(xml_string)
            tmp_in_path = tmp_in.name

        try:
            # Transform directly using stylesheet_file parameter (don't pre-compile)
            result = xslt_processor.transform_to_string(
                source_file=tmp_in_path,
                stylesheet_file=abs_xslt_path
            )

            # Check for transformation errors
            if xslt_processor.exception_occurred:
                error_msg = xslt_processor.error_message if xslt_processor.error_message else "Unknown transformation error"
                raise RuntimeError(f"Saxon transformation error: {error_msg}")

            if not result:
                raise RuntimeError("Saxon transformation returned empty result")

            return result

        finally:
            # Clean up input file
            if os.path.exists(tmp_in_path):
                os.unlink(tmp_in_path)

    def parse_svrl_output(self, svrl_tree):
        """
        Parse Schematron Validation Report Language (SVRL) output.

        Args:
            svrl_tree: XSLT transformation result (SVRL document)

        Returns:
            list: List of validation error dictionaries
        """
        errors = []
        svrl_ns = {'svrl': SVRL_NAMESPACE}

        # Handle both lxml trees and elements
        if isinstance(svrl_tree, str):
            svrl_tree = etree.fromstring(svrl_tree.encode('utf-8'))
        elif hasattr(svrl_tree, 'getroot'):
            svrl_tree = svrl_tree.getroot()

        # Find all failed assertions
        for failed_assert in svrl_tree.xpath('//svrl:failed-assert', namespaces=svrl_ns):
            # Extract error information
            rule_id = failed_assert.get('id', '')
            location = failed_assert.get('location', 'unknown')
            flag = failed_assert.get('flag', 'error')

            # Get error message from svrl:text element
            text_elem = failed_assert.find('svrl:text', namespaces=svrl_ns)
            message = text_elem.text.strip() if text_elem is not None and text_elem.text else 'No error message'

            # Map flag to severity
            severity = self._map_flag_to_severity(flag)

            errors.append({
                'stage': 'xslt',
                'severity': severity,
                'rule_id': rule_id,
                'message': message,
                'location': location,
                'line': None  # SVRL doesn't provide line numbers
            })

        # Find all successful reports (warnings/info)
        for report in svrl_tree.xpath('//svrl:successful-report', namespaces=svrl_ns):
            rule_id = report.get('id', '')
            location = report.get('location', 'unknown')
            flag = report.get('flag', 'warning')

            text_elem = report.find('svrl:text', namespaces=svrl_ns)
            message = text_elem.text.strip() if text_elem is not None and text_elem.text else 'No message'

            severity = self._map_flag_to_severity(flag)

            errors.append({
                'stage': 'xslt',
                'severity': severity,
                'rule_id': rule_id,
                'message': message,
                'location': location,
                'line': None
            })

        return errors

    def _map_flag_to_severity(self, flag):
        """
        Map SVRL flag to severity level.

        Args:
            flag: SVRL flag value (e.g., 'fatal', 'error', 'warning')

        Returns:
            str: Severity level
        """
        flag_lower = flag.lower() if flag else 'error'

        if flag_lower in ['fatal', 'error']:
            return 'error'
        elif flag_lower in ['warning', 'warn']:
            return 'warning'
        else:
            return 'info'

    def clear_cache(self):
        """Clear the XSLT cache."""
        self._xslt_cache.clear()
