"""多基金汇总净值表适配器。"""

from app.parsers.base import BaseTableParser
from app.parsers.models import WorkbookType


class FundNavSummaryParser(BaseTableParser):
    workbook_type = WorkbookType.FUND_NAV_SUMMARY

