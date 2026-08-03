"""归档附件的校验、解析与落库编排。"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Protocol

from sqlalchemy.orm import Session, sessionmaker

from app.db.models import AttachmentRecord, AttachmentStatus
from app.parsers.models import WorkbookParseResult
from app.services.persistence_service import NavPersistenceResult, NavPersistenceService

logger = logging.getLogger(__name__)


class WorkbookParser(Protocol):
    def parse_file(self, source_path: str | Path) -> WorkbookParseResult: ...


class AttachmentProcessingService:
    """解析前验证归档文件哈希，解析和入库失败均留下可追溯状态。"""

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        data_directory: Path,
        parser: WorkbookParser,
        persistence: NavPersistenceService | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.data_directory = data_directory.resolve()
        self.parser = parser
        self.persistence = persistence or NavPersistenceService()

    def process(self, attachment_id: int) -> NavPersistenceResult | None:
        with self.session_factory() as session:
            attachment = session.get(AttachmentRecord, attachment_id)
            if attachment is None:
                raise ValueError(f"附件记录不存在: {attachment_id}")
            if attachment.parse_status == AttachmentStatus.UNSUPPORTED:
                return None
            stored_path = attachment.stored_path
            expected_sha256 = attachment.sha256

        path = Path(stored_path)
        if not path.is_absolute():
            path = self.data_directory / path
        path = path.resolve()
        if not path.is_file():
            return self._record_failure(
                attachment_id,
                exception_type="attachment_missing",
                message="归档附件不存在，已停止解析",
                raw_data={"stored_path": stored_path},
            )

        try:
            actual_sha256 = self._sha256(path)
        except OSError as exc:
            return self._record_failure(
                attachment_id,
                exception_type="attachment_read_error",
                message=f"归档附件读取失败: {exc}",
                raw_data={"stored_path": stored_path},
            )
        if actual_sha256 != expected_sha256:
            return self._record_failure(
                attachment_id,
                exception_type="attachment_integrity_error",
                message="归档附件哈希与邮件入库记录不一致，已停止解析",
                raw_data={
                    "stored_path": stored_path,
                    "expected_sha256": expected_sha256,
                    "actual_sha256": actual_sha256,
                },
            )

        parse_result = self.parser.parse_file(path)
        with self.session_factory() as session, session.begin():
            return self.persistence.persist(
                session,
                attachment_id=attachment_id,
                result=parse_result,
            )

    def _record_failure(
        self,
        attachment_id: int,
        *,
        exception_type: str,
        message: str,
        raw_data: dict[str, str],
    ) -> NavPersistenceResult:
        logger.error(message, extra={"attachment_id": attachment_id})
        with self.session_factory() as session, session.begin():
            return self.persistence.persist_processing_failure(
                session,
                attachment_id=attachment_id,
                exception_type=exception_type,
                message=message,
                raw_data=raw_data,
            )

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
