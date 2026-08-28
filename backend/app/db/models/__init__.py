"""数据库模型统一导出，确保 Alembic 能发现全部 metadata。"""

from app.db.models.account_opening import (
    AccountApplication,
    ApplicationEvent,
    ApplicationRequirement,
    ApplicationSupplement,
    CounterpartyInstitution,
    RequirementTemplate,
    RequirementTemplateItem,
)
from app.db.models.app_user import AppUser
from app.db.models.audit_event import AuditEvent
from app.db.models.data_governance import (
    DocumentRelation,
    Entity,
    FieldDefinition,
    FieldValue,
    FundProductProfile,
    OrganizationProfile,
    ProductMaterialAttribution,
    ResourceGrant,
    SourceDocument,
)
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
from app.db.models.filing_profile import FilingField, FilingFileVersion, FilingProfile
from app.db.models.fund_nav import FundNav
from app.db.models.fund_product import FundProduct
from app.db.models.job_run import JobRun
from app.db.models.mailbox_account import MailboxAccount
from app.db.models.parse_workflow import (
    AttachmentParseTask,
    FundNavRevision,
    ParseResultRow,
    ParseSession,
)
from app.db.models.report_field import (
    ReportFieldDefinition,
    ReportFieldDefinitionVersion,
    ReportFieldValue,
)
from app.db.models.reporting import (
    ProductDocument,
    ReportBatch,
    ReportBatchItem,
    ReportDefinition,
    ReportFileVersion,
    ReportRun,
    ReportTemplate,
    ReportTemplateVersion,
)
from app.db.models.tenant import MailboxUserGrant, Tenant, TenantMembership

__all__ = [
    "AppUser",
    "AccountApplication",
    "ApplicationEvent",
    "ApplicationRequirement",
    "ApplicationSupplement",
    "AuditEvent",
    "AttachmentRecord",
    "AttachmentParseTask",
    "AttachmentStatus",
    "EmailRecord",
    "EmailStatus",
    "Entity",
    "CounterpartyInstitution",
    "ExceptionRecord",
    "ExceptionSeverity",
    "ExceptionStatus",
    "FilingProfile",
    "FilingField",
    "FilingFileVersion",
    "FieldDefinition",
    "FieldValue",
    "FundProductProfile",
    "FundNav",
    "FundNavRevision",
    "FundProduct",
    "JobRun",
    "JobStatus",
    "JobType",
    "MailboxAccount",
    "MailboxUserGrant",
    "ProductDocument",
    "OrganizationProfile",
    "ProductMaterialAttribution",
    "DocumentRelation",
    "ParseResultRow",
    "ParseSession",
    "ReportDefinition",
    "ReportBatch",
    "ReportBatchItem",
    "ReportFileVersion",
    "ReportFieldDefinition",
    "ReportFieldDefinitionVersion",
    "ReportFieldValue",
    "ReportRun",
    "ReportTemplate",
    "ReportTemplateVersion",
    "RequirementTemplate",
    "RequirementTemplateItem",
    "ResourceGrant",
    "SourceDocument",
    "Tenant",
    "TenantMembership",
    "TriggerType",
    "UserRole",
]
