"""标准库 MIME 邮件解析。"""

from __future__ import annotations

from email import policy
from email.parser import BytesParser
from email.utils import parseaddr

from app.email.models import EmailAttachment, MailboxMessage, ParsedEmail


class MimeMessageParser:
    """解析主题、发送人和全部带文件名的 MIME 附件。"""

    def parse(self, source: MailboxMessage) -> ParsedEmail:
        message = BytesParser(policy=policy.default).parsebytes(source.raw_message)
        subject = str(message.get("Subject") or "").strip()
        sender_header = str(message.get("From") or "").strip()
        _, sender_address = parseaddr(sender_header)
        sender = sender_address or sender_header
        message_id = str(message.get("Message-ID") or "").strip()

        attachments: list[EmailAttachment] = []
        for part_index, part in enumerate(message.walk(), start=1):
            filename = part.get_filename()
            disposition = part.get_content_disposition()
            if not filename and disposition != "attachment":
                continue

            payload = part.get_payload(decode=True)
            if payload is None:
                payload = b""
            attachments.append(
                EmailAttachment(
                    part_index=part_index,
                    original_name=str(filename or f"attachment-{part_index}.bin"),
                    content_type=part.get_content_type(),
                    content=payload,
                )
            )

        return ParsedEmail(
            subject=subject,
            sender=sender,
            receive_time=source.internal_date,
            message_id=message_id,
            attachments=tuple(attachments),
        )

