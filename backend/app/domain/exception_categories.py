"""运营异常的稳定分类规则。"""

_CATEGORY_LABELS = {
    "missing_date": "日期缺失",
    "invalid_date": "格式错误",
    "duplicate_row": "产品重复",
    "duplicate_nav": "产品重复",
    "empty_nav": "净值为空",
    "invalid_number": "格式错误",
    "missing_field": "格式错误",
    "ambiguous_format": "格式错误",
    "header_not_found": "格式错误",
    "workbook_read_error": "格式错误",
    "unsupported_workbook_format": "格式错误",
    "empty_workbook": "格式错误",
    "missing_product_code": "字段缺失",
    "missing_product_name": "字段缺失",
    "attachment_missing": "文件异常",
    "attachment_read_error": "文件异常",
    "attachment_integrity_error": "文件异常",
    "no_supported_excel_attachment": "文件异常",
    "mixed_workbook_types": "格式错误",
    "invalid_standard_record": "格式错误",
}


def exception_category(exception_type: str) -> str:
    return _CATEGORY_LABELS.get(exception_type, "其他异常")


def exception_types_for_category(category: str) -> tuple[str, ...]:
    """返回稳定分类对应的底层异常类型，供查询层复用。"""

    return tuple(
        exception_type
        for exception_type, label in _CATEGORY_LABELS.items()
        if label == category
    )


def known_exception_types() -> tuple[str, ...]:
    """返回已经显式分类的异常类型。未知类型统一归入“其他异常”。"""

    return tuple(_CATEGORY_LABELS)
