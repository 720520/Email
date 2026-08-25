"""基于真实文件签名选择 Excel 读取引擎。"""

from __future__ import annotations

from pathlib import Path
from zipfile import BadZipFile, ZipFile

import pandas as pd

from app.core.config import ExcelSettings

_XLSX_ZIP_SIGNATURE = b"PK\x03\x04"
_XLS_OLE_SIGNATURE = bytes.fromhex("D0CF11E0A1B11AE1")


class UnsupportedWorkbookFormatError(ValueError):
    pass


class WorkbookReadError(ValueError):
    pass


class WorkbookResourceLimitError(ValueError):
    pass


class WorkbookReader:
    """扩展名只作展示，实际读取引擎由文件头决定。"""

    def __init__(self, settings: ExcelSettings | None = None) -> None:
        self.settings = settings or ExcelSettings()

    def read(self, path: Path) -> dict[str, pd.DataFrame]:
        if not path.is_file():
            raise WorkbookReadError(f"Excel 文件不存在: {path}")
        file_size = path.stat().st_size
        if file_size > self.settings.max_workbook_bytes:
            raise WorkbookResourceLimitError(
                f"工作簿超过大小限制 ({file_size} > {self.settings.max_workbook_bytes})"
            )
        with path.open("rb") as source_file:
            signature = source_file.read(8)
        if signature.startswith(_XLSX_ZIP_SIGNATURE):
            engine = "openpyxl"
            self._validate_xlsx_archive(path, file_size)
        elif signature.startswith(_XLS_OLE_SIGNATURE):
            engine = "xlrd"
        else:
            raise UnsupportedWorkbookFormatError("文件不是受支持的 XLS 或 XLSX 工作簿")

        try:
            workbook = pd.ExcelFile(path, engine=engine)
            if len(workbook.sheet_names) > self.settings.max_sheets:
                raise WorkbookResourceLimitError(
                    f"工作表数量超过限制 ({len(workbook.sheet_names)} > {self.settings.max_sheets})"
                )
            sheets: dict[str, pd.DataFrame] = {}
            total_cells = 0
            for sheet_name in workbook.sheet_names:
                frame = pd.read_excel(
                    workbook,
                    sheet_name=sheet_name,
                    header=None,
                    dtype=object,
                    keep_default_na=False,
                    nrows=self.settings.max_rows_per_sheet + 1,
                )
                rows, columns = frame.shape
                if rows > self.settings.max_rows_per_sheet:
                    raise WorkbookResourceLimitError(
                        f"工作表 {sheet_name} 行数超过限制 "
                        f"({rows} > {self.settings.max_rows_per_sheet})"
                    )
                if columns > self.settings.max_columns:
                    raise WorkbookResourceLimitError(
                        f"工作表 {sheet_name} 列数超过限制 "
                        f"({columns} > {self.settings.max_columns})"
                    )
                total_cells += rows * columns
                if total_cells > self.settings.max_total_cells:
                    raise WorkbookResourceLimitError(
                        "工作簿单元格总数超过限制 "
                        f"({total_cells} > {self.settings.max_total_cells})"
                    )
                sheets[str(sheet_name)] = frame
        except Exception as exc:
            if isinstance(exc, WorkbookResourceLimitError):
                raise
            raise WorkbookReadError(f"Excel 工作簿读取失败: {exc}") from exc
        return sheets

    def _validate_xlsx_archive(self, path: Path, compressed_bytes: int) -> None:
        try:
            with ZipFile(path) as archive:
                uncompressed_bytes = sum(item.file_size for item in archive.infolist())
        except BadZipFile as exc:
            raise WorkbookReadError(f"XLSX 压缩包损坏: {exc}") from exc
        if uncompressed_bytes > self.settings.max_xlsx_uncompressed_bytes:
            raise WorkbookResourceLimitError(
                "XLSX 解压体积超过限制 "
                f"({uncompressed_bytes} > {self.settings.max_xlsx_uncompressed_bytes})"
            )
        ratio = uncompressed_bytes / max(compressed_bytes, 1)
        if ratio > self.settings.max_xlsx_compression_ratio:
            raise WorkbookResourceLimitError(
                f"XLSX 压缩比超过限制 ({ratio:.1f} > {self.settings.max_xlsx_compression_ratio})"
            )
