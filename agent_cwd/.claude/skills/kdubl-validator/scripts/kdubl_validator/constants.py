"""
KDUBL Document Type Mappings, Namespaces, and Validation Rules
"""

# UBL Namespaces
UBL_NAMESPACES = {
    'cbc': 'urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2',
    'cac': 'urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2',
    'ext': 'urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2',
    'invoice': 'urn:oasis:names:specification:ubl:schema:xsd:Invoice-2',
    'order': 'urn:oasis:names:specification:ubl:schema:xsd:Order-2',
    'svrl': 'http://purl.oclc.org/dsdl/svrl'
}

# Document Type Mappings
DOCUMENT_TYPES = {
    "Invoice": {
        "root_element": "Invoice",
        "namespace": "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2",
        "xsd_path": "Invoice/maindoc/UBL-Invoice-2.1.xsd",
        "xslt_path": "Invoice/KDUBL-validation.xslt",
        "ubl_version": "2.1",
        "customization_id": "urn:piaozone.com:ubl-2.1-customizations:v1.0",
        "profile_id": "urn:piaozone.com:ubl:invoice:v1.0"
    },
    "InvoiceResponse": {
        "root_element": "InvoiceResponse",
        "namespace": "urn:oasis:names:specification:ubl:schema:xsd:InvoiceResponse-2",
        "xsd_path": "InvoiceResponse/maindoc/UBL-InvoiceResponse-2.3.xsd",
        "xslt_path": "InvoiceResponse/KDUBL-validation.xslt",
        "ubl_version": "2.3",
        "customization_id": "urn:piaozone.com:ubl-2.3-customizations:v1.0",
        "profile_id": "urn:piaozone.com:ubl:invoiceresponse:v1.0"
    },
    "Order": {
        "root_element": "Order",
        "namespace": "urn:oasis:names:specification:ubl:schema:xsd:Order-2",
        "xsd_path": "Order/maindoc/UBL-Order-2.1.xsd",
        "xslt_path": "Order/KDUBL-validation.xslt",
        "ubl_version": "2.1",
        "customization_id": "urn:piaozone.com:ubl-2.1-customizations:v1.0",
        "profile_id": "urn:piaozone.com:ubl:order:v1.0"
    },
    "OrderBalance": {
        "root_element": "Order",
        "namespace": "urn:oasis:names:specification:ubl:schema:xsd:Order-2",
        "xsd_path": "OrderBalance/maindoc/UBL-Order-2.1.xsd",
        "xslt_path": "OrderBalance/KDUBL-validation.xslt",
        "ubl_version": "2.1",
        "customization_id": "urn:piaozone.com:ubl-2.1-customizations:v1.0",
        "profile_id": "urn:piaozone.com:ubl:order_balance:v1.0",
        "profile_id_alt": "urn:fdc:peppol.eu:poacc:trns:order_balance:3"
    },
    "OrderCancellation": {
        "root_element": "OrderCancellation",
        "namespace": "urn:oasis:names:specification:ubl:schema:xsd:OrderCancellation-2",
        "xsd_path": "OrderCancellation/maindoc/UBL-OrderCancellation-2.1.xsd",
        "xslt_path": "OrderCancellation/KDUBL-validation.xslt",
        "ubl_version": "2.1",
        "customization_id": "urn:piaozone.com:ubl-2.1-customizations:v1.0",
        "profile_id": "urn:piaozone.com:ubl:ordercancellation:v1.0"
    },
    "OrderChange": {
        "root_element": "OrderChange",
        "namespace": "urn:oasis:names:specification:ubl:schema:xsd:OrderChange-2",
        "xsd_path": "OrderChange/maindoc/UBL-OrderChange-2.1.xsd",
        "xslt_path": "OrderChange/KDUBL-validation.xslt",
        "ubl_version": "2.1",
        "customization_id": "urn:piaozone.com:ubl-2.1-customizations:v1.0",
        "profile_id": "urn:piaozone.com:ubl:orderchange:v1.0"
    },
    "OrderOnly": {
        "root_element": "Order",
        "namespace": "urn:oasis:names:specification:ubl:schema:xsd:Order-2",
        "xsd_path": "OrderOnly/maindoc/UBL-Order-2.1.xsd",
        "xslt_path": "OrderOnly/KDUBL-validation.xslt",
        "ubl_version": "2.1",
        "customization_id": "urn:piaozone.com:ubl-2.1-customizations:v1.0",
        "profile_id": "urn:piaozone.com:ubl:order_only:v1.0",
        "profile_id_alt": "urn:fdc:peppol.eu:poacc:trns:order_only:3"
    },
    "OrderResponse": {
        "root_element": "OrderResponse",
        "namespace": "urn:oasis:names:specification:ubl:schema:xsd:OrderResponse-2",
        "xsd_path": "OrderResponse/maindoc/UBL-OrderResponse-2.1.xsd",
        "xslt_path": "OrderResponse/KDUBL-validation.xslt",
        "ubl_version": "2.1",
        "customization_id": "urn:piaozone.com:ubl-2.1-customizations:v1.0",
        "profile_id": "urn:piaozone.com:ubl:orderresponse:v1.0"
    }
}

# Validation Rules Metadata
VALIDATION_RULES = {
    "KDUBL-R-CUSTOM-001": {
        "description": "CustomizationID 必须存在且非空",
        "severity": "fatal",
        "element": "CustomizationID",
        "fix_suggestion": "添加 CustomizationID 元素，值为对应文档类型的 customization_id"
    },
    "KDUBL-R-CUSTOM-002": {
        "description": "CustomizationID 必须匹配期望值",
        "severity": "fatal",
        "element": "CustomizationID",
        "fix_suggestion": "将 CustomizationID 修改为正确的值"
    },
    "KDUBL-R-PROFILE-001": {
        "description": "ProfileID 必须存在且非空",
        "severity": "fatal",
        "element": "ProfileID",
        "fix_suggestion": "添加 ProfileID 元素，值为对应文档类型的 profile_id"
    },
    "KDUBL-R-PROFILE-002": {
        "description": "ProfileID 必须匹配期望值",
        "severity": "fatal",
        "element": "ProfileID",
        "fix_suggestion": "将 ProfileID 修改为正确的值"
    },
    "KDUBL-R-002b": {
        "description": "IssueDate 格式必须为 YYYY-MM-DD",
        "severity": "fatal",
        "element": "IssueDate",
        "fix_suggestion": "使用 YYYY-MM-DD 格式（例如：2025-01-15）"
    },
    "KDUBL-R-002c": {
        "description": "IssueTime 必须包含时区（HH:MM:SS±HH:MM）",
        "severity": "fatal",
        "element": "IssueTime",
        "fix_suggestion": "添加时区信息，例如：09:30:47+01:00"
    },
    "KDUBL-R-003": {
        "description": "文档必须包含 ID 元素",
        "severity": "fatal",
        "element": "ID",
        "fix_suggestion": "添加唯一的文档 ID"
    },
    "KDUBL-R-004": {
        "description": "供应商信息必须完整",
        "severity": "error",
        "element": "AccountingSupplierParty",
        "fix_suggestion": "确保包含供应商名称、地址和联系信息"
    },
    "KDUBL-R-005": {
        "description": "客户信息必须完整",
        "severity": "error",
        "element": "AccountingCustomerParty",
        "fix_suggestion": "确保包含客户名称、地址和联系信息"
    }
}

# Severity Levels
SEVERITY_LEVELS = {
    "fatal": 3,
    "error": 2,
    "warning": 1,
    "info": 0
}

# SVRL Namespace
SVRL_NAMESPACE = "http://purl.oclc.org/dsdl/svrl"
