"""基于真实文件签名选择 Excel 读取引擎。"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

_XLSX_ZIP_SIGNATURE = b"PK\x03\x04"
_XLS_OLE_SIGNATURE = bytes.fromhex("D0CF11E0A1B11AE1")


class UnsupportedWorkbookFormatError(ValueError):
    pass


class WorkbookReadError(ValueError):
    pass


class WorkbookReader:
    """扩展名只作展示，实际读取引擎由文件头决定。"""

    def read(self, path: Path) -> dict[str, pd.DataFrame]:
        if not path.is_file():
            raise WorkbookReadError(f"Excel 文件不存在: {path}")
        with path.open("rb") as source_file:
            signature = source_file.read(8)
        if signature.startswith(_XLSX_ZIP_SIGNATURE):
            engine = "openpyxl"
        elif signature.startswith(_XLS_OLE_SIGNATURE):
            engine = "xlrd"
        else:
            raise UnsupportedWorkbookFormatError("文件不是受支持的 XLS 或 XLSX 工作簿")

        try:
            sheets = pd.read_excel(
                path,
                sheet_name=None,
                header=None,
                dtype=object,
                engine=engine,
                keep_default_na=False,
            )
        except Exception as exc:
            raise WorkbookReadError(f"Excel 工作簿读取失败: {exc}") from exc
        return {str(name): frame for name, frame in sheets.items()}
