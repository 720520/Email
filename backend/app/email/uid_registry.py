"""基于文件系统的 IMAP UID 幂等登记。"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class FileUidRegistry:
    """通过原子创建占位文件防止同一 UID 被并发或重复处理。

    阶段 5 接入 email_record 唯一约束后，该实现仍可作为调度进程的第一层互斥。
    """

    def __init__(self, root: Path, *, stale_seconds: int = 1800) -> None:
        self.root = root
        self.stale_seconds = stale_seconds

    def reserve(self, mailbox_key: str, uid: int) -> bool:
        mailbox_directory = self.root / mailbox_key
        mailbox_directory.mkdir(parents=True, exist_ok=True)
        done_path = self._done_path(mailbox_key, uid)
        processing_path = self._processing_path(mailbox_key, uid)
        if done_path.exists():
            return False

        if processing_path.exists() and not self._is_stale(processing_path):
            return False
        if processing_path.exists():
            try:
                processing_path.unlink()
            except FileNotFoundError:
                pass

        try:
            with processing_path.open("x", encoding="utf-8") as handle:
                json.dump({"reserved_at": datetime.now(UTC).isoformat()}, handle)
                handle.flush()
                os.fsync(handle.fileno())
        except FileExistsError:
            return False

        if done_path.exists():
            processing_path.unlink(missing_ok=True)
            return False
        return True

    def complete(self, mailbox_key: str, uid: int, metadata: dict[str, Any]) -> None:
        payload = {
            "uid": uid,
            "completed_at": datetime.now(UTC).isoformat(),
            **metadata,
        }
        self._atomic_write_json(self._done_path(mailbox_key, uid), payload)
        self._processing_path(mailbox_key, uid).unlink(missing_ok=True)

    def release(self, mailbox_key: str, uid: int) -> None:
        self._processing_path(mailbox_key, uid).unlink(missing_ok=True)

    def is_complete(self, mailbox_key: str, uid: int) -> bool:
        return self._done_path(mailbox_key, uid).exists()

    def _done_path(self, mailbox_key: str, uid: int) -> Path:
        return self.root / mailbox_key / f"{uid}.done.json"

    def _processing_path(self, mailbox_key: str, uid: int) -> Path:
        return self.root / mailbox_key / f"{uid}.processing"

    def _is_stale(self, path: Path) -> bool:
        age_seconds = datetime.now(UTC).timestamp() - path.stat().st_mtime
        return age_seconds >= self.stale_seconds

    @staticmethod
    def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = path.with_suffix(f"{path.suffix}.{os.getpid()}.tmp")
        try:
            with temporary_path.open("w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_path, path)
        finally:
            temporary_path.unlink(missing_ok=True)

