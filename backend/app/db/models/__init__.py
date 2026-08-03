"""数据库模型统一导出，确保 Alembic 能发现全部 metadata。"""

from app.db.models.app_user import AppUser
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
from app.db.models.job_run import JobRun

__all__ = [
    "AppUser",
    "AttachmentRecord",
    "AttachmentStatus",
    "EmailRecord",
    "EmailStatus",
    "ExceptionRecord",
    "ExceptionSeverity",
    "ExceptionStatus",
    "FundNav",
    "JobRun",
    "JobStatus",
    "JobType",
    "TriggerType",
    "UserRole",
]
