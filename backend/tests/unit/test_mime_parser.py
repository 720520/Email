from datetime import UTC, datetime
from email.message import EmailMessage

from app.email.mime_parser import MimeMessageParser
from app.email.models import MailboxMessage


def test_parse_chinese_subject_sender_and_attachment() -> None:
    message = EmailMessage()
    message["Subject"] = "【基金净值】吉余测试基金"
    message["From"] = "托管运营 <custodian@example.com>"
    message["To"] = "fund@example.com"
    message["Message-ID"] = "<nav-100@example.com>"
    message.set_content("请查收附件。")
    message.add_attachment(
        b"excel-content",
        maintype="application",
        subtype="vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename="基金每日净值表_20260724.xlsx",
    )
    source = MailboxMessage(
        uid=100,
        internal_date=datetime(2026, 7, 24, 10, 0, tzinfo=UTC),
        raw_message=message.as_bytes(),
    )

    parsed = MimeMessageParser().parse(source)

    assert parsed.subject == "【基金净值】吉余测试基金"
    assert parsed.sender == "custodian@example.com"
    assert parsed.message_id == "<nav-100@example.com>"
    assert len(parsed.attachments) == 1
    assert parsed.attachments[0].original_name == "基金每日净值表_20260724.xlsx"
    assert parsed.attachments[0].content == b"excel-content"


def test_parse_html_nav_body_and_octet_stream_xls_attachment() -> None:
    """华泰邮件正文展示净值表，同时把旧版 xls 作为二进制附件发送。"""

    message = EmailMessage()
    message["Subject"] = "吉余测试基金_F001_基金每日净值表2026-07-31"
    message["From"] = "托管平台 <custodian@example.com>"
    message["To"] = "fund@example.com"
    message.set_content("产品净值如下，请查阅。")
    message.add_alternative(
        """
        <html><body><table>
          <tr><th>日期</th><th>资产代码</th><th>资产名称</th><th>资产份额净值(元)</th></tr>
          <tr><td>2026-07-31</td><td>F001</td><td>吉余测试基金</td><td>0.7071</td></tr>
        </table></body></html>
        """,
        subtype="html",
    )
    message.add_attachment(
        b"legacy-xls-content",
        maintype="application",
        subtype="octet-stream",
        filename="吉余测试基金_F001_基金每日净值表_2026-07-31.xls",
    )
    source = MailboxMessage(
        uid=101,
        internal_date=datetime(2026, 8, 3, 7, 28, tzinfo=UTC),
        raw_message=message.as_bytes(),
    )

    parsed = MimeMessageParser().parse(source)

    assert len(parsed.attachments) == 1
    attachment = parsed.attachments[0]
    assert attachment.content_type == "application/octet-stream"
    assert attachment.original_name.endswith("_2026-07-31.xls")
    assert attachment.content == b"legacy-xls-content"
