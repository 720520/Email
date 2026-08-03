"""单基金每日净值表适配器。"""

from app.parsers.base import BaseTableParser
from app.parsers.models import WorkbookType


class SingleFundDailyParser(BaseTableParser):
    workbook_type = WorkbookType.SINGLE_FUND_DAILY

