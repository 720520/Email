"""数据库模型统一导出，确保 Alembic 能发现全部 metadata。"""

from app.db.models.app_user import AppUser
from app.db.models.audit_event import AuditEvent
from app.db.models.email_record import AttachmentRecord, EmailRecord
from app.db.models.enums import (
    AttachmentStatus,
    EmailStatus,
    ExceptionSeverity,
    ExceptionStatus,
    JobStatus,
    JobType,
    TriggerType,
    UserRole,
)
from app.db.models.exception_record import ExceptionRecord
from app.db.models.fund_nav import FundNav
from app.db.models.fund_product import FundProduct
from app.db.models.job_run import JobRun
from app.db.models.mailbox_account import MailboxAccount
from app.db.models.tenant import MailboxUserGrant, Tenant, TenantMembership

__all__ = [
    "AppUser",
    "AuditEvent",
    "AttachmentRecord",
    "AttachmentStatus",
    "EmailRecord",
    "EmailStatus",
    "ExceptionRecord",
    "ExceptionSeverity",
    "ExceptionStatus",
    "FundNav",
    "FundProduct",
    "JobRun",
    "JobStatus",
    "JobType",
    "MailboxAccount",
    "MailboxUserGrant",
    "Tenant",
    "TenantMembership",
    "TriggerType",
    "UserRole",
]
