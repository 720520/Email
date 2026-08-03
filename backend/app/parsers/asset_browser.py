"""基金资产净值浏览表适配器。"""

from app.parsers.base import BaseTableParser
from app.parsers.models import WorkbookType


class AssetNavBrowserParser(BaseTableParser):
    workbook_type = WorkbookType.ASSET_NAV_BROWSER

