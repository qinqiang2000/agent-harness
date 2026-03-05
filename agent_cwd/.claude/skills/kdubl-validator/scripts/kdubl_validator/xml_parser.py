"""
XML Parsing and Document Type Detection
"""

from lxml import etree
from .constants import DOCUMENT_TYPES, UBL_NAMESPACES
from .config import check_file_size


def parse_xml(xml_input, input_type='path'):
    """
    Parse XML from file path or string content.

    Args:
        xml_input: File path or XML content string
        input_type: 'path' or 'content'

    Returns:
        lxml.etree._ElementTree: Parsed XML tree

    Raises:
        ValueError: If input_type is invalid or XML is malformed
        FileNotFoundError: If file path doesn't exist
    """
    try:
        if input_type == 'path':
            # Check file size
            check_file_size(xml_input)
            # Parse from file
            parser = etree.XMLParser(remove_blank_text=False, resolve_entities=False)
            tree = etree.parse(xml_input, parser)
        elif input_type == 'content':
            # Parse from string
            parser = etree.XMLParser(remove_blank_text=False, resolve_entities=False)
            tree = etree.fromstring(xml_input.encode('utf-8'), parser)
            tree = tree.getroottree()
        else:
            raise ValueError(f"Invalid input_type: {input_type}. Must be 'path' or 'content'")

        return tree

    except etree.XMLSyntaxError as e:
        raise ValueError(f"XML 格式错误: {str(e)}")
    except FileNotFoundError:
        raise FileNotFoundError(f"文件不存在: {xml_input}")
    except Exception as e:
        raise ValueError(f"解析 XML 时出错: {str(e)}")


def detect_document_type(xml_tree):
    """
    Detect the KDUBL document type based on root element and namespace.

    Args:
        xml_tree: Parsed XML tree

    Returns:
        tuple: (document_type_name, document_type_config)

    Raises:
        ValueError: If document type cannot be determined
    """
    root = xml_tree.getroot()
    root_tag = etree.QName(root.tag).localname
    root_namespace = etree.QName(root.tag).namespace

    # First pass: match by root element and namespace
    for doc_type, config in DOCUMENT_TYPES.items():
        if (config['root_element'] == root_tag and
                config['namespace'] == root_namespace):

            # Special handling for Order variants (Order, OrderOnly, OrderBalance)
            if root_tag == 'Order':
                variant = detect_order_variant(xml_tree)
                if variant:
                    return variant, DOCUMENT_TYPES[variant]

            return doc_type, config

    # If no match found
    raise ValueError(
        f"未知的文档类型: 根元素={root_tag}, 命名空间={root_namespace}\n"
        f"支持的文档类型: {', '.join(DOCUMENT_TYPES.keys())}"
    )


def detect_order_variant(xml_tree):
    """
    Detect the specific Order variant (Order, OrderOnly, or OrderBalance).

    Args:
        xml_tree: Parsed XML tree with Order root element

    Returns:
        str or None: Detected variant name or None if it's a standard Order
    """
    root = xml_tree.getroot()

    # Try to find ProfileID element
    profile_id_elem = root.find('.//{urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2}ProfileID')

    if profile_id_elem is not None and profile_id_elem.text:
        profile_text = profile_id_elem.text.lower()

        # Check for OrderOnly
        if 'order_only' in profile_text or 'orderonly' in profile_text:
            return 'OrderOnly'

        # Check for OrderBalance
        if 'order_balance' in profile_text or 'orderbalance' in profile_text:
            return 'OrderBalance'

    # Try CustomizationID as fallback
    customization_id_elem = root.find('.//{urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2}CustomizationID')

    if customization_id_elem is not None and customization_id_elem.text:
        custom_text = customization_id_elem.text.lower()

        if 'order_only' in custom_text or 'orderonly' in custom_text:
            return 'OrderOnly'

        if 'order_balance' in custom_text or 'orderbalance' in custom_text:
            return 'OrderBalance'

    # Default to standard Order
    return 'Order'


def get_element_location(element):
    """
    Get the XPath location of an element.

    Args:
        element: lxml Element

    Returns:
        str: XPath expression
    """
    try:
        tree = element.getroottree()
        return tree.getpath(element)
    except Exception:
        return 'unknown'


def get_element_line_number(element):
    """
    Get the line number of an element in the source XML.

    Args:
        element: lxml Element

    Returns:
        int or None: Line number or None if not available
    """
    return element.sourceline if hasattr(element, 'sourceline') else None
