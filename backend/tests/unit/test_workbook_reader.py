from pathlib import Path

import pandas as pd
import pytest

from app.parsers.workbook_reader import (
    UnsupportedWorkbookFormatError,
    WorkbookReader,
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
    source.write_bytes(signature)
    calls = []

    def fake_read_excel(path, **kwargs):
        calls.append((path, kwargs))
        return {"Sheet1": pd.DataFrame([["ok"]])}

    monkeypatch.setattr(pd, "read_excel", fake_read_excel)

    sheets = WorkbookReader().read(source)

    assert list(sheets) == ["Sheet1"]
    assert calls[0][1]["engine"] == expected_engine


def test_reject_unknown_binary_format(tmp_path: Path) -> None:
    source = tmp_path / "fake.xlsx"
    source.write_bytes(b"not-an-excel-file")

    with pytest.raises(UnsupportedWorkbookFormatError):
        WorkbookReader().read(source)

