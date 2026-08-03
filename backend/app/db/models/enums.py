"""数据库状态枚举。"""

from enum import StrEnum


class EmailStatus(StrEnum):
    DISCOVERED = "discovered"
    ARCHIVED = "archived"
    PROCESSING = "processing"
    SUCCESS = "success"
    PARTIAL_SUCCESS = "partial_success"
    FAILED = "failed"
    SKIPPED = "skipped"


class AttachmentStatus(StrEnum):
    PENDING = "pending"
    ARCHIVED = "archived"
    PARSING = "parsing"
    SUCCESS = "success"
    PARTIAL_SUCCESS = "partial_success"
    FAILED = "failed"
    DUPLICATE = "duplicate"
    UNSUPPORTED = "unsupported"


class ExceptionStatus(StrEnum):
    OPEN = "open"
    RESOLVED = "resolved"
    IGNORED = "ignored"


class ExceptionSeverity(StrEnum):
    WARNING = "warning"
    ERROR = "error"


class JobStatus(StrEnum):
    RUNNING = "running"
    SUCCESS = "success"
    PARTIAL_SUCCESS = "partial_success"
    FAILED = "failed"


class JobType(StrEnum):
    MAIL_SYNC = "mail_sync"
    ATTACHMENT_REPARSE = "attachment_reparse"
    MANUAL_UPLOAD = "manual_upload"
    EXPORT = "export"


class TriggerType(StrEnum):
    SCHEDULED = "scheduled"
    MANUAL = "manual"
    STARTUP_RECOVERY = "startup_recovery"


class UserRole(StrEnum):
    ADMIN = "admin"
    OPERATOR = "operator"
    VIEWER = "viewer"
