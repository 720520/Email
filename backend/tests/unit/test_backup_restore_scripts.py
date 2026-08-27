from __future__ import annotations

import os
import subprocess
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]


def _run(script: str, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(PROJECT_ROOT / "scripts" / script), *arguments],
        cwd=PROJECT_ROOT,
        env={**os.environ, "LC_ALL": "C.UTF-8"},
        check=False,
        capture_output=True,
        text=True,
    )


def test_backup_and_restore_round_trip(tmp_path: Path) -> None:
    source = tmp_path / "source"
    backups = tmp_path / "backups"
    restored = tmp_path / "restored"
    source.mkdir()
    (source / "fund_nav.db").write_bytes(b"sqlite-test-database")
    (source / "tenants/1/filing").mkdir(parents=True)
    (source / "tenants/1/filing/document.pdf").write_bytes(b"synthetic-pdf")

    backup = _run(
        "backup.sh",
        "--data-dir",
        str(source),
        "--backup-root",
        str(backups),
        "--label",
        "stage-0-test",
    )
    assert backup.returncode == 0, backup.stderr

    restore = _run(
        "restore.sh",
        "--backup",
        str(backups / "stage-0-test"),
        "--data-dir",
        str(restored),
    )
    assert restore.returncode == 0, restore.stderr
    assert (restored / "fund_nav.db").read_bytes() == b"sqlite-test-database"
    assert (restored / "tenants/1/filing/document.pdf").read_bytes() == b"synthetic-pdf"


def test_restore_rejects_tampered_backup(tmp_path: Path) -> None:
    source = tmp_path / "source"
    backups = tmp_path / "backups"
    source.mkdir()
    (source / "fund_nav.db").write_bytes(b"original")
    backup = _run(
        "backup.sh",
        "--data-dir",
        str(source),
        "--backup-root",
        str(backups),
        "--label",
        "tamper-test",
    )
    assert backup.returncode == 0, backup.stderr
    (backups / "tamper-test/data/fund_nav.db").write_bytes(b"tampered")

    restore = _run(
        "restore.sh",
        "--backup",
        str(backups / "tamper-test"),
        "--data-dir",
        str(tmp_path / "restored"),
    )
    assert restore.returncode != 0
    assert "校验失败" in restore.stderr
