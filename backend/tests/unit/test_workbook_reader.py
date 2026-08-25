from pathlib import Path
from zipfile import ZipFile

import pandas as pd
import pytest

from app.core.config import ExcelSettings
from app.parsers.workbook_reader import (
    UnsupportedWorkbookFormatError,
    WorkbookReader,
    WorkbookResourceLimitError,
)


@pytest.mark.parametrize(
    ("signature", "expected_engine"),
    [
        (b"PK\x03\x04fake", "openpyxl"),
        (bytes.fromhex("D0CF11E0A1B11AE1"), "xlrd"),
    ],
)
def test_select_engine_by_file_signature_not_filename(
    tmp_path: Path,
    monkeypatch,
    signature: bytes,
    expected_engine: str,
) -> None:
    source = tmp_path / "misleading-name.bin"
    if signature.startswith(b"PK"):
        with ZipFile(source, "w") as archive:
            archive.writestr("dummy.xml", "ok")
    else:
        source.write_bytes(signature)
    calls = []

    class FakeExcelFile:
        sheet_names = ["Sheet1"]

    def fake_excel_file(path, **kwargs):
        calls.append((path, kwargs))
        return FakeExcelFile()

    def fake_read_excel(workbook, **kwargs):
        assert isinstance(workbook, FakeExcelFile)
        return pd.DataFrame([["ok"]])

    monkeypatch.setattr(pd, "ExcelFile", fake_excel_file)
    monkeypatch.setattr(pd, "read_excel", fake_read_excel)

    sheets = WorkbookReader().read(source)

    assert list(sheets) == ["Sheet1"]
    assert calls[0][1]["engine"] == expected_engine


def test_reject_unknown_binary_format(tmp_path: Path) -> None:
    source = tmp_path / "fake.xlsx"
    source.write_bytes(b"not-an-excel-file")

    with pytest.raises(UnsupportedWorkbookFormatError):
        WorkbookReader().read(source)


def test_reject_workbook_over_file_size_limit(tmp_path: Path) -> None:
    source = tmp_path / "oversized.xlsx"
    source.write_bytes(b"PK\x03\x04" + b"x" * 2048)

    with pytest.raises(WorkbookResourceLimitError, match="工作簿超过大小限制"):
        WorkbookReader(ExcelSettings(max_workbook_bytes=1024)).read(source)
