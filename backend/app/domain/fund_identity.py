"""基金名称与份额类别的展示归一化。"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

_NAMED_CLASS_PATTERNS = (
    re.compile(
        r"^(?P<base>.+?)[_\-\s]*[（(]?(?P<class>[A-Z])(?:类|级)?份额[）)]?$",
        re.IGNORECASE,
    ),
    re.compile(r"^(?P<base>.+?)\((?P<class>[ABC])(?:类|级)\)$", re.IGNORECASE),
    re.compile(r"^(?P<base>.+?)(?P<class>[ABC])(?:类|级)$", re.IGNORECASE),
    re.compile(r"^(?P<base>.+(?:基金|计划))(?P<class>[ABC])$", re.IGNORECASE),
)
_CODE_CLASS_PATTERN = re.compile(r"\((?P<class>[ABC])(?:类|级)\)$", re.IGNORECASE)
_TOTAL_CODE_PATTERN = re.compile(r"\(总\)$")
_CODE_QUALIFIER_PATTERN = re.compile(r"\((?:总|[ABC](?:类|级))\)$", re.IGNORECASE)
_PLAIN_CODE_CLASS_PATTERN = re.compile(r"(?P<base>.+?)(?P<class>[A-Z])$", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class FundDisplayIdentity:
    """用于页面分组的基金主体名称和标准份额类别。"""

    group_name: str
    share_class: str | None


def fund_display_identity(product_name: str, product_code: str) -> FundDisplayIdentity:
    """识别常见 A/B/C 类或级后缀，不改变数据库中的原始名称和代码。"""

    normalized_name = unicodedata.normalize("NFKC", product_name).strip()
    normalized_code = unicodedata.normalize("NFKC", product_code).strip()
    for pattern in _NAMED_CLASS_PATTERNS:
        match = pattern.fullmatch(normalized_name)
        if match is not None:
            return FundDisplayIdentity(
                group_name=match.group("base").strip(),
                share_class=f"{match.group('class').upper()}类",
            )

    code_match = _CODE_CLASS_PATTERN.search(normalized_code)
    if _TOTAL_CODE_PATTERN.search(normalized_code):
        share_class = "总份额"
    else:
        share_class = (
            f"{code_match.group('class').upper()}类" if code_match is not None else None
        )
    return FundDisplayIdentity(group_name=normalized_name, share_class=share_class)


def fund_display_sort_key(product_name: str, product_code: str) -> tuple[str, int, str, str]:
    """同一基金相邻展示，普通份额在前，随后依次为 A/B/C 类。"""

    identity = fund_display_identity(product_name, product_code)
    class_order = {"总份额": 0, None: 1, "A类": 2, "B类": 3, "C类": 4}
    return (
        identity.group_name.casefold(),
        class_order.get(identity.share_class, 99),
        product_name.casefold(),
        product_code.casefold(),
    )


def master_product_identity(
    *,
    product_name: str,
    product_code: str,
    registration_code: str | None = None,
    parent_product_code: str | None = None,
    parent_product_name: str | None = None,
) -> tuple[str, str]:
    """确定基金主体身份；份额代码保留在净值快照，主档优先采用备案代码。"""

    display = fund_display_identity(product_name, product_code)
    fallback_code = _CODE_QUALIFIER_PATTERN.sub("", product_code).strip()
    if display.share_class and display.share_class != "总份额":
        plain_match = _PLAIN_CODE_CLASS_PATTERN.fullmatch(fallback_code)
        if (
            plain_match is not None
            and f"{plain_match.group('class').upper()}类" == display.share_class
        ):
            fallback_code = plain_match.group("base")
    master_code = registration_code or parent_product_code or fallback_code
    master_name = parent_product_name or display.group_name
    return master_code.strip().upper(), master_name.strip()
