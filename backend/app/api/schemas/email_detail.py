"""邮件详情响应模型。"""

from datetime import datetime

from pydantic import BaseModel

from app.db.models import AttachmentStatus, EmailStatus


class EmailAttachmentDetail(BaseModel):
    id: int
    original_name: str
    file_type: str | None
    parse_status: AttachmentStatus
    error_message: str | None


class EmailDetailResponse(BaseModel):
    id: int
    subject: str
    sender: str
    receive_time: datetime
    status: EmailStatus
    error_message: str | None
    attachments: list[EmailAttachmentDetail]
    body_text: str
    body_truncated: bool
    original_available: bool
