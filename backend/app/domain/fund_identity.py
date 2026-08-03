"""基金名称与份额类别的展示归一化。"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

_NAMED_CLASS_PATTERNS = (
    re.compile(r"^(?P<base>.+?)\((?P<class>[ABC])(?:类|级)\)$", re.IGNORECASE),
    re.compile(r"^(?P<base>.+?)(?P<class>[ABC])(?:类|级)$", re.IGNORECASE),
    re.compile(r"^(?P<base>.+(?:基金|计划))(?P<class>[ABC])$", re.IGNORECASE),
)
_CODE_CLASS_PATTERN = re.compile(r"\((?P<class>[ABC])(?:类|级)\)$", re.IGNORECASE)


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
    share_class = (
        f"{code_match.group('class').upper()}类" if code_match is not None else None
    )
    return FundDisplayIdentity(group_name=normalized_name, share_class=share_class)


def fund_display_sort_key(product_name: str, product_code: str) -> tuple[str, int, str, str]:
    """同一基金相邻展示，普通份额在前，随后依次为 A/B/C 类。"""

    identity = fund_display_identity(product_name, product_code)
    class_order = {None: 0, "A类": 1, "B类": 2, "C类": 3}
    return (
        identity.group_name.casefold(),
        class_order.get(identity.share_class, 99),
        product_name.casefold(),
        product_code.casefold(),
    )
