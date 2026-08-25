"""人工解析暂存、修正、校验与确认入库。"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.core.credential_security import audit_signing_key
from app.db.models import (
    AttachmentRecord,
    AttachmentStatus,
    EmailRecord,
    EmailStatus,
    FundNav,
    FundNavRevision,
    ParseResultRow,
    ParseSession,
    UserRole,
)
from app.db.session import configure_tenant_scope
from app.domain.fund_identity import master_product_identity
from app.parsers.models import (
    ParseIssue,
    StandardNavRecord,
    WorkbookParseResult,
    WorkbookType,
)
from app.services.audit_service import AuditService
from app.services.persistence_service import NavPersistenceResult, NavPersistenceService

_EDITABLE_FIELDS = {
    "product_name",
    "product_code",
    "asset_code",
    "registration_code",
    "share_class",
    "nav_date",
    "unit_nav",
    "total_nav",
    "asset_value",
    "asset_share",
    "paid_in_capital",
    "holding_shares",
    "reference_market_value",
    "total_assets",
    "total_assets_nav_ratio",
    "investor_name",
    "investor_account",
    "parent_unit_nav",
    "parent_total_nav",
    "parent_asset_value",
    "parent_product_code",
    "parent_product_name",
    "notes",
    "parent_paid_in_capital",
    "investment_manager_info",
    "investment_strategy_info",
}
_NAV_FIELDS = (
    "product_name",
    "product_code",
    "master_product_code",
    "asset_code",
    "registration_code",
    "share_class",
    "nav_date",
    "unit_nav",
    "total_nav",
    "asset_value",
    "asset_share",
    "paid_in_capital",
    "holding_shares",
    "reference_market_value",
    "total_assets",
    "total_assets_nav_ratio",
    "investor_name",
    "investor_account",
    "parent_unit_nav",
    "parent_total_nav",
    "parent_asset_value",
    "parent_product_code",
    "parent_product_name",
    "notes",
    "parent_paid_in_capital",
)


class ParseReviewError(ValueError):
    pass


class ParseReviewConflictError(ParseReviewError):
    pass


class ParseReviewService:
    def __init__(
        self,
        settings: Settings,
        session_factory: sessionmaker[Session],
        *,
        tenant_id: int,
        mailbox_account_id: int,
        actor_user_id: int,
        actor_username: str,
    ) -> None:
        self.settings = settings
        self.session_factory = session_factory
        self.tenant_id = tenant_id
        self.mailbox_account_id = mailbox_account_id
        self.actor_user_id = actor_user_id
        self.actor_username = actor_username
        self.audit = AuditService(audit_signing_key(settings.security))

    def create_session(
        self,
        *,
        attachment_id: int,
        source_attachment_id: int | None,
        result: WorkbookParseResult,
    ) -> int:
        with self.session_factory() as session, session.begin():
            self._scope(session)
            attachment = session.get(AttachmentRecord, attachment_id)
            if attachment is None:
                raise ParseReviewError("附件记录不存在")
            review = ParseSession(
                tenant_id=self.tenant_id,
                mailbox_account_id=self.mailbox_account_id,
                attachment_id=attachment_id,
                source_attachment_id=source_attachment_id,
                created_by_user_id=self.actor_user_id,
                status="review_required",
                parser_version=self.settings.excel.parser_version,
                file_issues=[
                    _issue_dict(issue) for issue in result.issues if issue.row_number is None
                ],
            )
            session.add(review)
            session.flush()
            for parsed_row in result.rows:
                record = parsed_row.record
                values = _record_values(record)
                master_code = None
                if record.product_code and record.product_name:
                    master_code, _ = master_product_identity(
                        product_name=record.product_name,
                        product_code=record.product_code,
                        registration_code=record.registration_code,
                        parent_product_code=record.parent_product_code,
                        parent_product_name=record.parent_product_name,
                    )
                row = ParseResultRow(
                    tenant_id=self.tenant_id,
                    mailbox_account_id=self.mailbox_account_id,
                    parse_session_id=review.id,
                    source_sheet=record.source_sheet,
                    source_row=record.source_row,
                    source_type=record.source_type.value,
                    master_product_code=master_code,
                    issues=[_issue_dict(issue) for issue in parsed_row.issues],
                    original_data=_json_safe(values),
                    **values,
                )
                session.add(row)
            session.flush()
            self._validate_session(session, review)
            attachment.parse_status = AttachmentStatus.ARCHIVED
            email = session.get(EmailRecord, attachment.email_id)
            if email is not None:
                email.status = EmailStatus.ARCHIVED
                email.error_message = "人工解析结果等待确认"
            self.audit.append(
                session,
                tenant_id=self.tenant_id,
                actor_user_id=self.actor_user_id,
                actor_username=self.actor_username,
                mailbox_account_id=self.mailbox_account_id,
                action="parse.review.create",
                resource_type="parse_session",
                resource_id=review.id,
                outcome=review.status,
                detail={
                    "attachment_id": attachment_id,
                    "row_count": review.row_count,
                    "valid_count": review.valid_count,
                    "invalid_count": review.invalid_count,
                    "parser_version": review.parser_version,
                },
            )
            return review.id

    def get_session(self, parse_session_id: int) -> tuple[ParseSession, tuple[ParseResultRow, ...]]:
        with self.session_factory() as session:
            self._scope(session)
            review = session.get(ParseSession, parse_session_id)
            if review is None:
                raise ParseReviewError("解析会话不存在")
            rows = tuple(
                session.scalars(
                    select(ParseResultRow)
                    .where(ParseResultRow.parse_session_id == review.id)
                    .order_by(
                        ParseResultRow.source_sheet, ParseResultRow.source_row, ParseResultRow.id
                    )
                )
            )
            session.expunge_all()
            return review, rows

    def update_row(
        self,
        *,
        parse_session_id: int,
        row_id: int,
        values: dict[str, Any],
        ignored: bool | None,
        conflict_action: str | None,
        edit_reason: str,
        expected_version: int,
    ) -> tuple[ParseSession, ParseResultRow]:
        if not edit_reason.strip():
            raise ParseReviewError("人工修正必须填写原因")
        unknown = set(values) - _EDITABLE_FIELDS
        if unknown:
            raise ParseReviewError(f"包含不可修改字段: {', '.join(sorted(unknown))}")
        if conflict_action not in {None, "unresolved", "keep_existing", "replace_existing"}:
            raise ParseReviewError("重复数据处理方式无效")
        with self.session_factory() as session, session.begin():
            self._scope(session)
            review = session.get(ParseSession, parse_session_id)
            row = session.get(ParseResultRow, row_id)
            if review is None or row is None or row.parse_session_id != parse_session_id:
                raise ParseReviewError("解析结果行不存在")
            if review.status in {"committed", "cancelled"}:
                raise ParseReviewConflictError("该解析会话已结束，不能继续修改")
            if row.row_version != expected_version:
                raise ParseReviewConflictError("该行已被其他操作更新，请刷新后重试")
            before = _row_snapshot(row)
            identity_changed = bool({"product_code", "nav_date"}.intersection(values))
            for field_name, value in values.items():
                setattr(row, field_name, _clean_value(field_name, value))
            if ignored is not None:
                row.status = "ignored" if ignored else "valid"
            if identity_changed and conflict_action is None:
                row.conflict_action = "unresolved"
            if conflict_action is not None:
                row.conflict_action = conflict_action
            row.is_edited = True
            row.edit_reason = edit_reason.strip()[:500]
            row.edited_by_user_id = self.actor_user_id
            row.row_version += 1
            self._validate_row(session, row)
            self._validate_session(session, review)
            after = _row_snapshot(row)
            self.audit.append(
                session,
                tenant_id=self.tenant_id,
                actor_user_id=self.actor_user_id,
                actor_username=self.actor_username,
                mailbox_account_id=self.mailbox_account_id,
                action="parse.review.row.update",
                resource_type="parse_result_row",
                resource_id=row.id,
                outcome=row.status,
                detail={"reason": row.edit_reason, "before": before, "after": after},
            )
            session.flush()
            session.expunge(review)
            session.expunge(row)
            return review, row

    def validate(self, parse_session_id: int) -> tuple[ParseSession, tuple[ParseResultRow, ...]]:
        with self.session_factory() as session, session.begin():
            self._scope(session)
            review = session.get(ParseSession, parse_session_id)
            if review is None:
                raise ParseReviewError("解析会话不存在")
            if review.status == "committed":
                raise ParseReviewConflictError("该解析会话已经确认入库")
            self._validate_session(session, review)
        return self.get_session(parse_session_id)

    def confirm(self, parse_session_id: int, *, role: UserRole) -> NavPersistenceResult:
        with self.session_factory() as session, session.begin():
            self._scope(session)
            review = session.get(ParseSession, parse_session_id)
            if review is None:
                raise ParseReviewError("解析会话不存在")
            if review.status == "committed":
                raise ParseReviewConflictError("该解析会话已经确认入库")
            rows = list(
                session.scalars(
                    select(ParseResultRow)
                    .where(ParseResultRow.parse_session_id == review.id)
                    .order_by(ParseResultRow.id)
                )
            )
            self._validate_session(session, review, rows=rows)
            unresolved = [
                row
                for row in rows
                if row.status == "invalid"
                or (row.status == "duplicate" and row.conflict_action == "unresolved")
            ]
            if unresolved:
                raise ParseReviewConflictError(
                    f"仍有 {len(unresolved)} 行未通过校验或未选择重复处理方式"
                )
            replacements = [
                row
                for row in rows
                if row.status == "duplicate" and row.conflict_action == "replace_existing"
            ]
            if replacements and role != UserRole.ADMIN:
                raise ParseReviewConflictError("历史正式净值更正仅允许租户管理员确认")
            attachment = session.get(AttachmentRecord, review.attachment_id)
            if attachment is None:
                raise ParseReviewError("解析附件不存在")

            for row in replacements:
                self._replace_existing(session, review, row, attachment)

            new_rows = [row for row in rows if row.status == "valid"]
            if new_rows:
                parse_result = WorkbookParseResult(
                    source_path=self._attachment_path(attachment),
                    rows=[],
                )
                # 人工修正后的行全部重新校验过，因此以无解析错误的标准记录提交。
                from app.parsers.models import ParsedNavRow

                parse_result.rows = [
                    ParsedNavRow(record=self._standard_record(row, attachment)) for row in new_rows
                ]
                persisted = NavPersistenceService().persist(
                    session,
                    attachment_id=attachment.id,
                    result=parse_result,
                )
            else:
                attachment.parse_status = (
                    AttachmentStatus.SUCCESS if replacements else AttachmentStatus.DUPLICATE
                )
                attachment.error_message = None if replacements else "人工确认保留已有重复记录"
                self._refresh_email(session, attachment.email_id, attachment.parse_status)
                persisted = NavPersistenceResult(
                    attachment_id=attachment.id,
                    inserted_count=0,
                    duplicate_count=len([row for row in rows if row.status == "duplicate"]),
                    exception_count=0,
                    status=attachment.parse_status,
                )

            inserted = {
                (item.product_code, item.nav_date): item
                for item in session.scalars(
                    select(FundNav).where(FundNav.attachment_id == attachment.id)
                )
            }
            for row in new_rows:
                nav = inserted.get(((row.product_code or "").strip().upper(), row.nav_date))
                if nav is not None:
                    row.status = "committed"
                    row.committed_nav_id = nav.id
                else:
                    row.status = "duplicate"
            for row in rows:
                if row.status == "duplicate" and row.conflict_action == "keep_existing":
                    row.status = "kept_existing"

            review.status = "committed"
            review.confirmed_by_user_id = self.actor_user_id
            review.confirmed_at = datetime.now(UTC)
            review.inserted_count = persisted.inserted_count
            review.duplicate_count = sum(
                row.status in {"duplicate", "kept_existing", "replaced"} for row in rows
            )
            review.error_message = attachment.error_message
            self.audit.append(
                session,
                tenant_id=self.tenant_id,
                actor_user_id=self.actor_user_id,
                actor_username=self.actor_username,
                mailbox_account_id=self.mailbox_account_id,
                action="parse.review.commit",
                resource_type="parse_session",
                resource_id=review.id,
                outcome=persisted.status.value,
                detail={
                    "attachment_id": attachment.id,
                    "inserted_count": review.inserted_count,
                    "duplicate_count": review.duplicate_count,
                    "replacement_count": len(replacements),
                    "ignored_count": review.ignored_count,
                    "parser_version": review.parser_version,
                },
            )
            return persisted

    def _validate_session(
        self,
        session: Session,
        review: ParseSession,
        *,
        rows: list[ParseResultRow] | None = None,
    ) -> None:
        if rows is None:
            rows = list(
                session.scalars(
                    select(ParseResultRow).where(ParseResultRow.parse_session_id == review.id)
                )
            )
        seen: set[tuple[str, Any]] = set()
        for row in rows:
            if row.status == "ignored":
                continue
            self._validate_row(session, row)
            if row.product_code and row.nav_date:
                key = (row.product_code.strip().upper(), row.nav_date)
                if key in seen:
                    row.status = "invalid"
                    row.validation_message = "暂存结果中产品代码和净值日期重复"
                seen.add(key)
        review.row_count = len(rows)
        review.valid_count = sum(row.status == "valid" for row in rows)
        review.invalid_count = sum(row.status == "invalid" for row in rows)
        review.ignored_count = sum(row.status == "ignored" for row in rows)
        review.duplicate_count = sum(row.status == "duplicate" for row in rows)
        blocking_file_issues = [
            item for item in review.file_issues if item.get("severity") == "error"
        ]
        review.status = (
            "invalid"
            if review.invalid_count or blocking_file_issues or not rows
            else "ready"
            if not any(
                row.status == "duplicate" and row.conflict_action == "unresolved" for row in rows
            )
            else "review_required"
        )
        review.error_message = (
            f"{review.invalid_count} 行未通过校验"
            if review.invalid_count
            else "文件级解析错误尚未解决"
            if blocking_file_issues
            else None
        )

    def _validate_row(self, session: Session, row: ParseResultRow) -> None:
        if row.status == "ignored":
            row.validation_message = None
            row.existing_nav_id = None
            return
        errors = []
        if not (row.product_name or "").strip():
            errors.append("产品名称不能为空")
        if not (row.product_code or "").strip():
            errors.append("产品代码不能为空")
        if row.nav_date is None:
            errors.append("净值日期不能为空")
        if all(value is None for value in (row.unit_nav, row.total_nav, row.asset_value)):
            errors.append("单位净值、累计净值、资产净值至少填写一项")
        for name in (
            "unit_nav",
            "total_nav",
            "asset_value",
            "asset_share",
            "paid_in_capital",
            "total_assets",
        ):
            value = getattr(row, name)
            if value is not None and value < 0:
                errors.append(f"{name} 不能为负数")
        if errors:
            row.status = "invalid"
            row.validation_message = "；".join(errors)
            row.existing_nav_id = None
            return
        row.product_code = row.product_code.strip().upper()
        row.product_name = row.product_name.strip()
        row.master_product_code, _ = master_product_identity(
            product_name=row.product_name,
            product_code=row.product_code,
            registration_code=row.registration_code,
            parent_product_code=row.parent_product_code,
            parent_product_name=row.parent_product_name,
        )
        existing = session.scalar(
            select(FundNav).where(
                FundNav.product_code == row.product_code,
                FundNav.nav_date == row.nav_date,
            )
        )
        if existing is not None:
            row.status = "duplicate"
            row.existing_nav_id = existing.id
            row.validation_message = "正式台账已存在相同产品代码和净值日期，请选择保留或更正"
        else:
            row.status = "valid"
            row.existing_nav_id = None
            row.conflict_action = "unresolved"
            row.validation_message = None

    def _replace_existing(
        self,
        session: Session,
        review: ParseSession,
        row: ParseResultRow,
        attachment: AttachmentRecord,
    ) -> None:
        existing = session.get(FundNav, row.existing_nav_id) if row.existing_nav_id else None
        if existing is None:
            raise ParseReviewConflictError("待更正的正式净值已不存在，请重新校验")
        if not (row.edit_reason or "").strip():
            raise ParseReviewConflictError("更正历史正式净值必须填写原因")
        before = _nav_snapshot(existing)
        standard = self._standard_record(row, attachment)
        master_code, _ = master_product_identity(
            product_name=standard.product_name or "",
            product_code=standard.product_code or "",
            registration_code=standard.registration_code,
            parent_product_code=standard.parent_product_code,
            parent_product_name=standard.parent_product_name,
        )
        for field_name in _NAV_FIELDS:
            if field_name == "master_product_code":
                setattr(existing, field_name, master_code)
            elif hasattr(standard, field_name):
                setattr(existing, field_name, getattr(standard, field_name))
        existing.source_file = attachment.original_name
        existing.source_sheet = row.source_sheet
        existing.source_row = row.source_row
        existing.source_type = row.source_type
        existing.attachment_id = attachment.id
        after = _nav_snapshot(existing)
        session.add(
            FundNavRevision(
                tenant_id=self.tenant_id,
                mailbox_account_id=self.mailbox_account_id,
                fund_nav_id=existing.id,
                parse_session_id=review.id,
                parse_result_row_id=row.id,
                actor_user_id=self.actor_user_id,
                reason=row.edit_reason or "人工更正",
                original_data=before,
                corrected_data=after,
            )
        )
        row.status = "replaced"
        row.committed_nav_id = existing.id
        self.audit.append(
            session,
            tenant_id=self.tenant_id,
            actor_user_id=self.actor_user_id,
            actor_username=self.actor_username,
            mailbox_account_id=self.mailbox_account_id,
            action="fund_nav.correct",
            resource_type="fund_nav",
            resource_id=existing.id,
            outcome="success",
            detail={
                "reason": row.edit_reason,
                "before": before,
                "after": after,
                "parse_session_id": review.id,
            },
        )

    def _standard_record(
        self, row: ParseResultRow, attachment: AttachmentRecord
    ) -> StandardNavRecord:
        values = {name: getattr(row, name) for name in _EDITABLE_FIELDS}
        return StandardNavRecord(
            **values,
            source_file=attachment.original_name,
            source_sheet=row.source_sheet,
            source_row=row.source_row,
            source_type=WorkbookType(row.source_type),
            create_time=datetime.now(UTC),
        )

    def _attachment_path(self, attachment: AttachmentRecord) -> Path:
        path = Path(attachment.stored_path)
        return path if path.is_absolute() else self.settings.data_directory / path

    @staticmethod
    def _refresh_email(session: Session, email_id: int, status: AttachmentStatus) -> None:
        email = session.get(EmailRecord, email_id)
        if email is None:
            return
        email.status = (
            EmailStatus.SUCCESS if status == AttachmentStatus.SUCCESS else EmailStatus.FAILED
        )
        email.error_message = None if status == AttachmentStatus.SUCCESS else "人工确认未新增净值"

    def _scope(self, session: Session) -> None:
        configure_tenant_scope(
            session,
            tenant_id=self.tenant_id,
            mailbox_ids=(self.mailbox_account_id,),
        )


def _record_values(record: StandardNavRecord) -> dict[str, Any]:
    return {name: getattr(record, name) for name in _EDITABLE_FIELDS}


def _issue_dict(issue: ParseIssue) -> dict[str, Any]:
    return {
        "code": issue.code.value,
        "severity": issue.severity.value,
        "message": issue.message,
        "sheet_name": issue.sheet_name,
        "row_number": issue.row_number,
        "field_name": issue.field_name,
        "raw_value": _json_safe(issue.raw_value),
        "raw_data": _json_safe(issue.raw_data),
    }


def _row_snapshot(row: ParseResultRow) -> dict[str, Any]:
    return _json_safe(
        {name: getattr(row, name) for name in sorted(_EDITABLE_FIELDS)}
        | {
            "status": row.status,
            "conflict_action": row.conflict_action,
        }
    )


def _nav_snapshot(nav: FundNav) -> dict[str, Any]:
    return _json_safe(
        {name: getattr(nav, name) for name in _NAV_FIELDS}
        | {
            "source_file": nav.source_file,
            "source_sheet": nav.source_sheet,
            "source_row": nav.source_row,
            "attachment_id": nav.attachment_id,
        }
    )


def _clean_value(field_name: str, value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip()
        return value or None
    return value


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (datetime,)):
        return value.isoformat()
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return str(value)
