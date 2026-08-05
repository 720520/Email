"""多邮箱账户、加密凭据和邮箱级授权管理。"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import EmailSettings, Settings
from app.core.credential_security import (
    MailboxCredentialCipher,
    dedicated_credential_key_configured,
)
from app.db.models import MailboxAccount, MailboxUserGrant, TenantMembership, UserRole


class MailboxAccountNotFoundError(ValueError):
    pass


class MailboxAccountConflictError(ValueError):
    pass


class DedicatedCredentialKeyRequiredError(ValueError):
    pass


class MailboxAccountService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.cipher = MailboxCredentialCipher.from_security_settings(settings.security)

    def list_accounts(
        self,
        session: Session,
        *,
        tenant_id: int,
        allowed_mailbox_ids: tuple[int, ...] | None = None,
    ) -> list[MailboxAccount]:
        conditions = [MailboxAccount.tenant_id == tenant_id]
        if allowed_mailbox_ids is not None:
            if not allowed_mailbox_ids:
                return []
            conditions.append(MailboxAccount.id.in_(allowed_mailbox_ids))
        return list(
            session.scalars(
                select(MailboxAccount)
                .where(*conditions)
                .order_by(
                    MailboxAccount.is_default.desc(),
                    MailboxAccount.is_enabled.desc(),
                    MailboxAccount.display_name,
                    MailboxAccount.id,
                )
            )
        )

    def get_account(
        self,
        session: Session,
        *,
        tenant_id: int,
        mailbox_account_id: int,
        allowed_mailbox_ids: tuple[int, ...] | None = None,
        require_enabled: bool = False,
    ) -> MailboxAccount:
        conditions = [
            MailboxAccount.id == mailbox_account_id,
            MailboxAccount.tenant_id == tenant_id,
        ]
        if allowed_mailbox_ids is not None:
            if mailbox_account_id not in allowed_mailbox_ids:
                raise MailboxAccountNotFoundError("邮箱不存在或当前用户没有访问权限")
        if require_enabled:
            conditions.append(MailboxAccount.is_enabled.is_(True))
        mailbox = session.scalar(select(MailboxAccount).where(*conditions))
        if mailbox is None:
            raise MailboxAccountNotFoundError("邮箱不存在或已停用")
        return mailbox

    def get_default(
        self,
        session: Session,
        *,
        tenant_id: int,
        allowed_mailbox_ids: tuple[int, ...],
    ) -> MailboxAccount:
        if not allowed_mailbox_ids:
            raise MailboxAccountNotFoundError("当前用户没有可访问的邮箱")
        mailbox = session.scalar(
            select(MailboxAccount)
            .where(
                MailboxAccount.tenant_id == tenant_id,
                MailboxAccount.id.in_(allowed_mailbox_ids),
                MailboxAccount.is_enabled.is_(True),
            )
            .order_by(MailboxAccount.is_default.desc(), MailboxAccount.id)
            .limit(1)
        )
        if mailbox is None:
            raise MailboxAccountNotFoundError("当前用户没有可用邮箱")
        return mailbox

    def create_account(
        self,
        session: Session,
        *,
        tenant_id: int,
        creator_user_id: int,
        values: dict[str, Any],
        credential: str | None,
    ) -> MailboxAccount:
        if values.get("use_ssl", True) and values.get("start_tls", False):
            raise MailboxAccountConflictError("SSL/TLS 与 STARTTLS 不能同时启用")
        self._assert_identity_available(session, tenant_id=tenant_id, values=values)
        existing = session.scalar(
            select(MailboxAccount.id).where(MailboxAccount.tenant_id == tenant_id).limit(1)
        )
        is_default = bool(values.pop("is_default", False)) or existing is None
        if is_default:
            self._clear_default(session, tenant_id=tenant_id)
        mailbox = MailboxAccount(
            tenant_id=tenant_id,
            provider_type=_provider_type(str(values.get("host", ""))),
            configuration_source="database",
            is_default=is_default,
            **values,
        )
        session.add(mailbox)
        session.flush()
        self._set_credential(mailbox, credential)
        session.add(
            MailboxUserGrant(
                tenant_id=tenant_id,
                mailbox_account_id=mailbox.id,
                user_id=creator_user_id,
                can_read_metadata=True,
                can_read_content=True,
                can_operate=True,
                can_manage_credentials=True,
                is_active=True,
            )
        )
        session.flush()
        return mailbox

    def update_account(
        self,
        session: Session,
        *,
        mailbox: MailboxAccount,
        values: dict[str, Any],
        credential: str | None,
        credential_supplied: bool,
        clear_credential: bool,
    ) -> MailboxAccount:
        effective_use_ssl = values.get("use_ssl", mailbox.use_ssl)
        effective_start_tls = values.get("start_tls", mailbox.start_tls)
        if effective_use_ssl and effective_start_tls:
            raise MailboxAccountConflictError("SSL/TLS 与 STARTTLS 不能同时启用")
        identity_values = {
            "host": values.get("host", mailbox.host),
            "username": values.get("username", mailbox.username),
            "folder": values.get("folder", mailbox.folder),
        }
        self._assert_identity_available(
            session,
            tenant_id=mailbox.tenant_id,
            values=identity_values,
            exclude_id=mailbox.id,
        )
        requested_default = values.pop("is_default", None)
        requested_enabled = values.get("is_enabled")
        if requested_default is True:
            self._clear_default(session, tenant_id=mailbox.tenant_id, exclude_id=mailbox.id)
            mailbox.is_default = True
        elif requested_default is False and mailbox.is_default:
            raise MailboxAccountConflictError("必须至少通过其他邮箱接替后才能取消默认邮箱")

        if requested_enabled is False and mailbox.is_default:
            replacement = session.scalar(
                select(MailboxAccount)
                .where(
                    MailboxAccount.tenant_id == mailbox.tenant_id,
                    MailboxAccount.id != mailbox.id,
                    MailboxAccount.is_enabled.is_(True),
                )
                .order_by(MailboxAccount.id)
                .limit(1)
            )
            mailbox.is_default = False
            session.flush()
            if replacement is not None:
                replacement.is_default = True

        for field, value in values.items():
            setattr(mailbox, field, value)
        if "host" in values:
            mailbox.provider_type = _provider_type(mailbox.host)
        mailbox.configuration_source = "database"
        if clear_credential:
            mailbox.credential_ciphertext = None
            mailbox.credential_updated_at = datetime.now(UTC)
        elif credential_supplied:
            self._set_credential(mailbox, credential)
        session.flush()
        return mailbox

    def runtime_settings(self, mailbox: MailboxAccount) -> EmailSettings:
        credential = ""
        if mailbox.credential_ciphertext:
            credential = self.cipher.decrypt(
                mailbox.credential_ciphertext,
                tenant_id=mailbox.tenant_id,
                mailbox_account_id=mailbox.id,
            )
        options = mailbox.parsing_options or {}
        common = dict(
            host=mailbox.host,
            port=mailbox.port,
            username=mailbox.username,
            auth_mode=mailbox.auth_mode,
            use_ssl=mailbox.use_ssl,
            start_tls=mailbox.start_tls,
            timeout_seconds=mailbox.timeout_seconds,
            folder=mailbox.folder,
            lookback_days=mailbox.lookback_days,
            max_messages_per_run=mailbox.max_messages_per_run,
            max_attachment_bytes=mailbox.max_attachment_bytes,
            retry_attempts=mailbox.retry_attempts,
            retry_base_delay_seconds=mailbox.retry_base_delay_seconds,
            uid_reservation_stale_seconds=mailbox.uid_reservation_stale_seconds,
            candidate_keywords=options.get(
                "candidate_keywords", self.settings.email.candidate_keywords
            ),
            excel_extensions=options.get("excel_extensions", self.settings.email.excel_extensions),
        )
        if mailbox.auth_mode == "oauth2":
            return EmailSettings(**common, oauth2_access_token=credential)
        return EmailSettings(**common, password=credential)

    def upsert_grant(
        self,
        session: Session,
        *,
        tenant_id: int,
        mailbox_account_id: int,
        user_id: int,
        values: dict[str, bool],
    ) -> MailboxUserGrant:
        membership = session.scalar(
            select(TenantMembership).where(
                TenantMembership.tenant_id == tenant_id,
                TenantMembership.user_id == user_id,
                TenantMembership.is_active.is_(True),
            )
        )
        if membership is None:
            raise MailboxAccountNotFoundError("目标用户不是当前租户的有效成员")
        if values.get("can_manage_credentials") and membership.role != UserRole.ADMIN:
            raise MailboxAccountConflictError("只有租户管理员可以获得邮箱凭据管理权限")
        grant = session.scalar(
            select(MailboxUserGrant).where(
                MailboxUserGrant.tenant_id == tenant_id,
                MailboxUserGrant.mailbox_account_id == mailbox_account_id,
                MailboxUserGrant.user_id == user_id,
            )
        )
        if grant is None:
            grant = MailboxUserGrant(
                tenant_id=tenant_id,
                mailbox_account_id=mailbox_account_id,
                user_id=user_id,
                **values,
            )
            session.add(grant)
        else:
            for field, value in values.items():
                setattr(grant, field, value)
        session.flush()
        return grant

    @staticmethod
    def update_connection_result(
        mailbox: MailboxAccount,
        *,
        success: bool,
        error_message: str | None = None,
    ) -> None:
        mailbox.last_connection_status = "success" if success else "failed"
        mailbox.last_connection_at = datetime.now(UTC)
        mailbox.last_connection_error = None if success else (error_message or "连接失败")[:1000]

    def _set_credential(self, mailbox: MailboxAccount, credential: str | None) -> None:
        if not credential:
            return
        if not dedicated_credential_key_configured(self.settings.security):
            raise DedicatedCredentialKeyRequiredError(
                "未配置独立邮箱凭据密钥，禁止保存邮箱授权码"
            )
        mailbox.credential_ciphertext = self.cipher.encrypt(
            credential,
            tenant_id=mailbox.tenant_id,
            mailbox_account_id=mailbox.id,
        )
        mailbox.credential_key_version = 1
        mailbox.credential_updated_at = datetime.now(UTC)

    @staticmethod
    def _assert_identity_available(
        session: Session,
        *,
        tenant_id: int,
        values: dict[str, Any],
        exclude_id: int | None = None,
    ) -> None:
        conditions = [
            MailboxAccount.tenant_id == tenant_id,
            MailboxAccount.host == str(values.get("host", "")).strip(),
            MailboxAccount.username == str(values.get("username", "")).strip(),
            MailboxAccount.folder == str(values.get("folder", "INBOX")).strip(),
        ]
        if exclude_id is not None:
            conditions.append(MailboxAccount.id != exclude_id)
        if session.scalar(select(MailboxAccount.id).where(*conditions).limit(1)) is not None:
            raise MailboxAccountConflictError("同一租户中该邮箱服务器、账号和目录已存在")

    @staticmethod
    def _clear_default(
        session: Session,
        *,
        tenant_id: int,
        exclude_id: int | None = None,
    ) -> None:
        conditions = [
            MailboxAccount.tenant_id == tenant_id,
            MailboxAccount.is_default.is_(True),
        ]
        if exclude_id is not None:
            conditions.append(MailboxAccount.id != exclude_id)
        session.execute(
            update(MailboxAccount)
            .where(*conditions)
            .values(is_default=False)
            .execution_options(synchronize_session="fetch")
        )


def _provider_type(host: str) -> str:
    normalized = host.casefold().strip()
    if "163.com" in normalized or "qiye.163.com" in normalized:
        return "netease_163"
    if "qq.com" in normalized:
        return "qq"
    if "outlook" in normalized or "office365" in normalized:
        return "outlook_oauth2"
    return "generic_imap"
