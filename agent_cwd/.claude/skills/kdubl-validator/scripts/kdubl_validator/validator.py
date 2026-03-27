"""
Core KDUBL Validator - Orchestrates validation pipeline
"""

from .xml_parser import parse_xml, detect_document_type
from .xsd_validator import XSDValidator
from .xslt_validator import XSLTValidator
from .report_generator import generate_report
from .config import validate_schema_path


class KDUBLValidator:
    """
    Main KDUBL XML validator that orchestrates the validation pipeline.

    Validation Pipeline:
    1. Parse XML (well-formedness check)
    2. Detect document type
    3. XSD schema validation
    4. XSLT business rules validation
    5. Generate comprehensive report
    """

    def __init__(self):
        """Initialize the validator with XSD and XSLT validators."""
        # Validate schema path on initialization
        try:
            validate_schema_path()
        except EnvironmentError as e:
            print(f"警告: {str(e)}")
            print("验证将在首次使用时失败，除非设置正确的路径。")

        self.xsd_validator = XSDValidator()
        self.xslt_validator = XSLTValidator()

    def validate(self, xml_input, input_type='path'):
        """
        Validate a KDUBL XML document through the complete pipeline.

        Args:
            xml_input: File path or XML content string
            input_type: 'path' or 'content'

        Returns:
            dict: Validation report with structure:
                {
                    'valid': bool,
                    'document_type': str,
                    'ubl_version': str,
                    'xml_file': str or None,
                    'errors': list,
                    'errors_by_stage': dict,
                    'summary': dict,
                    'total_errors': int
                }
        """
        errors = []
        doc_type = None
        doc_type_config = None
        xml_tree = None
        xml_file_name = xml_input if input_type == 'path' else None

        # Stage 1: Parse XML (well-formedness check)
        try:
            xml_tree = parse_xml(xml_input, input_type)
        except Exception as e:
            errors.append({
                'stage': 'wellformed',
                'severity': 'fatal',
                'message': str(e),
                'line': None,
                'location': 'document'
            })
            # Cannot continue without valid XML
            return generate_report('Unknown', {}, errors, xml_file_name)

        # Stage 2: Detect document type
        try:
            doc_type, doc_type_config = detect_document_type(xml_tree)
        except Exception as e:
            errors.append({
                'stage': 'detection',
                'severity': 'fatal',
                'message': str(e),
                'line': None,
                'location': 'document'
            })
            # Cannot continue without knowing document type
            return generate_report('Unknown', {}, errors, xml_file_name)

        # Stage 3: XSD schema validation
        try:
            xsd_errors = self.xsd_validator.validate(xml_tree, doc_type, doc_type_config)
            errors.extend(xsd_errors)
        except Exception as e:
            errors.append({
                'stage': 'xsd',
                'severity': 'fatal',
                'message': f"XSD 验证失败: {str(e)}",
                'line': None,
                'location': 'unknown'
            })

        # Stage 4: XSLT business rules validation
        # Continue even if XSD validation failed to collect all errors
        try:
            xslt_errors = self.xslt_validator.validate(xml_tree, doc_type, doc_type_config)
            errors.extend(xslt_errors)
        except Exception as e:
            errors.append({
                'stage': 'xslt',
                'severity': 'fatal',
                'message': f"XSLT 验证失败: {str(e)}",
                'line': None,
                'location': 'unknown'
            })

        # Stage 5: Generate report
        return generate_report(doc_type, doc_type_config, errors, xml_file_name)

    def clear_caches(self):
        """Clear all cached schemas and XSLT transforms."""
        self.xsd_validator.clear_cache()
        self.xslt_validator.clear_cache()
