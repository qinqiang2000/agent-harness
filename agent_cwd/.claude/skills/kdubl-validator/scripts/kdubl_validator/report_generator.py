"""
Validation Report Generation and Formatting
"""

from .constants import SEVERITY_LEVELS, VALIDATION_RULES


def generate_report(doc_type, doc_type_config, errors, xml_file_name=None):
    """
    Generate a structured validation report.

    Args:
        doc_type: Document type name
        doc_type_config: Document type configuration
        errors: List of validation error dictionaries
        xml_file_name: Optional XML file name for display

    Returns:
        dict: Structured validation report
    """
    # Count errors by severity
    summary = {
        'fatal': 0,
        'error': 0,
        'warning': 0,
        'info': 0
    }

    for error in errors:
        severity = error.get('severity', 'error')
        if severity in summary:
            summary[severity] += 1

    # Determine overall validity
    is_valid = summary['fatal'] == 0 and summary['error'] == 0

    # Group errors by stage
    errors_by_stage = {
        'wellformed': [],
        'detection': [],
        'xsd': [],
        'xslt': []
    }

    for error in errors:
        stage = error.get('stage', 'unknown')
        if stage in errors_by_stage:
            errors_by_stage[stage].append(error)

    # Sort errors by severity (fatal first)
    sorted_errors = sorted(
        errors,
        key=lambda e: SEVERITY_LEVELS.get(e.get('severity', 'error'), 2),
        reverse=True
    )

    # Build report
    report = {
        'valid': is_valid,
        'document_type': doc_type,
        'ubl_version': doc_type_config.get('ubl_version', 'unknown'),
        'xml_file': xml_file_name,
        'errors': sorted_errors,
        'errors_by_stage': errors_by_stage,
        'summary': summary,
        'total_errors': len(errors)
    }

    return report


def format_human_readable(report):
    """
    Format validation report as human-readable text.

    Args:
        report: Validation report dictionary

    Returns:
        str: Formatted text report
    """
    lines = []

    # Header
    lines.append("━" * 60)
    if report.get('xml_file'):
        lines.append(f"验证报告：{report['xml_file']}")
    else:
        lines.append("验证报告")

    lines.append(f"文档类型：{report['document_type']} (KDUBL {report['ubl_version']})")

    status = "✓ 有效" if report['valid'] else "✗ 无效"
    lines.append(f"状态：{status}")
    lines.append("━" * 60)

    # Summary
    summary = report['summary']
    if summary['fatal'] > 0 or summary['error'] > 0 or summary['warning'] > 0:
        lines.append(f"摘要：{summary['fatal']} 个致命错误，{summary['error']} 个错误，{summary['warning']} 个警告")
        lines.append("")

    # Errors by severity
    if summary['fatal'] > 0:
        lines.append("致命错误:")
        lines.append("━" * 60)
        for error in report['errors']:
            if error.get('severity') == 'fatal':
                lines.append(_format_error(error))
        lines.append("")

    if summary['error'] > 0:
        lines.append("错误:")
        lines.append("━" * 60)
        for error in report['errors']:
            if error.get('severity') == 'error':
                lines.append(_format_error(error))
        lines.append("")

    if summary['warning'] > 0:
        lines.append("警告:")
        lines.append("━" * 60)
        for error in report['errors']:
            if error.get('severity') == 'warning':
                lines.append(_format_error(error))
        lines.append("")

    # If no errors
    if report['total_errors'] == 0:
        lines.append("✓ 所有验证通过，未发现错误")
        lines.append("")

    lines.append("━" * 60)

    return "\n".join(lines)


def _format_error(error):
    """
    Format a single error message.

    Args:
        error: Error dictionary

    Returns:
        str: Formatted error message
    """
    lines = []

    # Error header
    stage = error.get('stage', 'unknown').upper()
    rule_id = error.get('rule_id', '')

    if rule_id:
        header = f"[{stage}] {rule_id}: {error['message']}"
    else:
        header = f"[{stage}] {error['message']}"

    lines.append(header)

    # Location info
    if error.get('line'):
        lines.append(f"    第 {error['line']} 行")

    if error.get('location') and error['location'] != 'unknown':
        lines.append(f"    位置: {error['location']}")

    # Add fix suggestion if available
    if rule_id and rule_id in VALIDATION_RULES:
        rule_info = VALIDATION_RULES[rule_id]
        if 'fix_suggestion' in rule_info:
            lines.append(f"    建议: {rule_info['fix_suggestion']}")

    return "\n".join(lines)


def format_error_summary(report):
    """
    Generate a brief error summary.

    Args:
        report: Validation report dictionary

    Returns:
        str: Brief summary text
    """
    if report['valid']:
        return f"✓ {report['document_type']} 文档验证通过"

    summary = report['summary']
    parts = []

    if summary['fatal'] > 0:
        parts.append(f"{summary['fatal']} 个致命错误")
    if summary['error'] > 0:
        parts.append(f"{summary['error']} 个错误")
    if summary['warning'] > 0:
        parts.append(f"{summary['warning']} 个警告")

    return f"✗ {report['document_type']} 文档验证失败：{', '.join(parts)}"
