"""默认租户、默认邮箱及现有用户授权的兼容引导。"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.credential_security import (
    MailboxCredentialCipher,
    audit_signing_key,
    dedicated_credential_key_configured,
)
from app.db.models import (
    MailboxAccount,
    Tenant,
)
from app.services.audit_service import AuditService

DEFAULT_TENANT_CODE = "default"
logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class FoundationIdentity:
    tenant_id: int
    mailbox_account_id: int


class FoundationService:
    """在开放多邮箱页面前，把现有单邮箱安全迁入默认业务账套。"""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.cipher = MailboxCredentialCipher.from_security_settings(settings.security)

    def ensure(self, session: Session) -> FoundationIdentity:
        """以显式受控旁路建立安全底座，完成后立即恢复默认拒绝策略。"""

        previous_skip = session.info.get("skip_tenant_scope")
        session.info["skip_tenant_scope"] = True
        try:
            return self._ensure_foundation(session)
        finally:
            if previous_skip is None:
                session.info.pop("skip_tenant_scope", None)
            else:
                session.info["skip_tenant_scope"] = previous_skip

    def _ensure_foundation(self, session: Session) -> FoundationIdentity:
        tenant = session.scalar(select(Tenant).where(Tenant.code == DEFAULT_TENANT_CODE))
        if tenant is None:
            tenant = Tenant(code=DEFAULT_TENANT_CODE, name="默认业务账套", is_active=True)
            session.add(tenant)
            session.flush()

        mailbox = session.scalar(
            select(MailboxAccount).where(
                MailboxAccount.tenant_id == tenant.id,
                MailboxAccount.is_default.is_(True),
            )
        )
        if mailbox is None:
            mailbox = MailboxAccount(
                tenant_id=tenant.id,
                display_name="默认邮箱",
                host="",
                username="",
                configuration_source="legacy",
                is_default=True,
                is_enabled=True,
            )
            session.add(mailbox)
            session.flush()

        credential_migrated = (
            self._sync_legacy_email_config(mailbox)
            if mailbox.configuration_source == "legacy"
            else False
        )
        if credential_migrated:
            previous_skip = session.info.get("skip_tenant_scope")
            session.info["skip_tenant_scope"] = True
            try:
                AuditService(audit_signing_key(self.settings.security)).append(
                    session,
                    tenant_id=tenant.id,
                    actor_user_id=None,
                    actor_username="system",
                    mailbox_account_id=mailbox.id,
                    action="mailbox.credential.bootstrap",
                    resource_type="mailbox_account",
                    resource_id=mailbox.id,
                    outcome="success",
                    detail={"credential_key_version": mailbox.credential_key_version},
                )
            finally:
                if previous_skip is None:
                    session.info.pop("skip_tenant_scope", None)
                else:
                    session.info["skip_tenant_scope"] = previous_skip
        session.flush()
        return FoundationIdentity(tenant.id, mailbox.id)

    def _sync_legacy_email_config(self, mailbox: MailboxAccount) -> bool:
        """过渡阶段继续把全局配置同步到默认邮箱，后续由邮箱管理页替代。"""

        source = self.settings.email
        mailbox.display_name = source.username or "默认邮箱"
        mailbox.provider_type = _provider_type(source.host)
        mailbox.host = source.host.strip()
        mailbox.port = source.port
        mailbox.username = source.username.strip()
        mailbox.auth_mode = source.auth_mode
        mailbox.use_ssl = source.use_ssl
        mailbox.start_tls = source.start_tls
        mailbox.timeout_seconds = source.timeout_seconds
        mailbox.folder = source.folder
        mailbox.lookback_days = source.lookback_days
        mailbox.max_messages_per_run = source.max_messages_per_run
        mailbox.max_attachment_bytes = source.max_attachment_bytes
        mailbox.retry_attempts = source.retry_attempts
        mailbox.retry_base_delay_seconds = source.retry_base_delay_seconds
        mailbox.uid_reservation_stale_seconds = source.uid_reservation_stale_seconds
        mailbox.parsing_options = {
            "candidate_keywords": list(source.candidate_keywords),
            "excel_extensions": list(source.excel_extensions),
        }
        credential = (
            source.oauth2_access_token.get_secret_value()
            if source.auth_mode == "oauth2"
            else source.password.get_secret_value()
        )
        if credential and not dedicated_credential_key_configured(self.settings.security):
            logger.warning("未配置独立邮箱凭据密钥，已跳过旧配置凭据入库")
            return False
        if credential and not self._credential_matches(mailbox, credential):
            mailbox.credential_ciphertext = self.cipher.encrypt(
                credential,
                tenant_id=mailbox.tenant_id,
                mailbox_account_id=mailbox.id,
            )
            mailbox.credential_key_version = 1
            mailbox.credential_updated_at = datetime.now(UTC)
            return True
        return False

    def _credential_matches(self, mailbox: MailboxAccount, credential: str) -> bool:
        if not mailbox.credential_ciphertext:
            return False
        try:
            return self.cipher.decrypt(
                mailbox.credential_ciphertext,
                tenant_id=mailbox.tenant_id,
                mailbox_account_id=mailbox.id,
            ) == credential
        except ValueError:
            return False


def _provider_type(host: str) -> str:
    normalized = host.casefold().strip()
    if "163.com" in normalized or "qiye.163.com" in normalized:
        return "netease_163"
    if "qq.com" in normalized:
        return "qq"
    if "outlook" in normalized or "office365" in normalized:
        return "outlook_oauth2"
    return "generic_imap"
