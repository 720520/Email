import os
from pathlib import Path

from app.email.uid_registry import FileUidRegistry


def test_uid_reservation_completion_and_duplicate_detection(tmp_path: Path) -> None:
    registry = FileUidRegistry(tmp_path, stale_seconds=60)

    assert registry.reserve("mailbox", 100) is True
    assert registry.reserve("mailbox", 100) is False

    registry.complete("mailbox", 100, {"status": "archived"})

    assert registry.is_complete("mailbox", 100) is True
    assert registry.reserve("mailbox", 100) is False


def test_release_allows_retry_and_stale_reservation_can_be_reclaimed(tmp_path: Path) -> None:
    registry = FileUidRegistry(tmp_path, stale_seconds=60)
    assert registry.reserve("mailbox", 101) is True
    registry.release("mailbox", 101)
    assert registry.reserve("mailbox", 101) is True

    processing_path = tmp_path / "mailbox/101.processing"
    os.utime(processing_path, (0, 0))
    assert registry.reserve("mailbox", 101) is True

