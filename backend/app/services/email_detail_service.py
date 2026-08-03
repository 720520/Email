"""归档邮件详情读取与安全正文预览。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from email import policy
from email.message import Message
from email.parser import BytesParser
from html.parser import HTMLParser
from pathlib import Path

MAX_PREVIEW_SOURCE_BYTES = 25 * 1024 * 1024
MAX_BODY_CHARACTERS = 100_000


class InvalidEmailArchivePathError(ValueError):
    """数据库中的邮件路径越过了受信任的数据目录。"""


class EmailPreviewTooLargeError(ValueError):
    """原始邮件过大，不适合加载到内存生成正文预览。"""


@dataclass(frozen=True, slots=True)
class EmailBodyPreview:
    text: str
    truncated: bool


class _PlainTextHTMLParser(HTMLParser):
    """把 HTML 邮件转换为纯文本，并忽略脚本、样式等非正文节点。"""

    _BLOCK_TAGS = {
        "address",
        "article",
        "aside",
        "blockquote",
        "br",
        "div",
        "footer",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "header",
        "hr",
        "li",
        "p",
        "section",
        "table",
        "td",
        "th",
        "tr",
    }
    _IGNORED_TAGS = {"head", "script", "style", "svg"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.fragments: list[str] = []
        self._ignored_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        normalized = tag.casefold()
        if normalized in self._IGNORED_TAGS:
            self._ignored_depth += 1
            return
        if self._ignored_depth == 0 and normalized in self._BLOCK_TAGS:
            self.fragments.append("\n")

    def handle_endtag(self, tag: str) -> None:
        normalized = tag.casefold()
        if normalized in self._IGNORED_TAGS:
            self._ignored_depth = max(0, self._ignored_depth - 1)
            return
        if self._ignored_depth == 0 and normalized in self._BLOCK_TAGS:
            self.fragments.append("\n")

    def handle_data(self, data: str) -> None:
        if self._ignored_depth == 0:
            self.fragments.append(data)

    def text(self) -> str:
        return _normalize_text("".join(self.fragments))


class EmailDetailService:
    """从归档 EML 中安全读取正文，不暴露或执行邮件 HTML。"""

    def __init__(self, data_directory: Path) -> None:
        self.data_directory = data_directory.resolve()

    def resolve_archive_path(self, stored_path: str | None) -> Path | None:
        if not stored_path:
            return None
        candidate = Path(stored_path)
        if not candidate.is_absolute():
            candidate = self.data_directory / candidate
        resolved = candidate.resolve()
        try:
            resolved.relative_to(self.data_directory)
        except ValueError as exc:
            raise InvalidEmailArchivePathError("邮件归档路径不在数据目录内") from exc
        return resolved if resolved.is_file() else None

    def body_preview(self, archive_path: Path | None) -> EmailBodyPreview:
        if archive_path is None:
            return EmailBodyPreview(text="", truncated=False)
        if archive_path.stat().st_size > MAX_PREVIEW_SOURCE_BYTES:
            raise EmailPreviewTooLargeError("原始邮件超过正文预览大小限制")

        message = BytesParser(policy=policy.default).parsebytes(archive_path.read_bytes())
        plain_parts: list[str] = []
        html_parts: list[str] = []
        for part in message.walk():
            if part.is_multipart() or _is_attachment(part):
                continue
            content_type = part.get_content_type().casefold()
            if content_type == "text/plain":
                plain_parts.append(_part_text(part))
            elif content_type == "text/html":
                html_parts.append(_part_text(part))

        if plain_parts:
            text = _normalize_text("\n\n".join(part for part in plain_parts if part))
        else:
            parser = _PlainTextHTMLParser()
            parser.feed("\n".join(part for part in html_parts if part))
            parser.close()
            text = parser.text()
        return _truncate(text)


def _is_attachment(part: Message) -> bool:
    return part.get_content_disposition() == "attachment" or bool(part.get_filename())


def _part_text(part: Message) -> str:
    try:
        content = part.get_content()
        if isinstance(content, str):
            return content
    except (LookupError, UnicodeDecodeError, ValueError):
        pass

    payload = part.get_payload(decode=True)
    if not isinstance(payload, bytes):
        return str(payload or "")
    charset = part.get_content_charset() or "utf-8"
    try:
        return payload.decode(charset, errors="replace")
    except LookupError:
        return payload.decode("utf-8", errors="replace")


def _normalize_text(value: str) -> str:
    normalized = value.replace("\r\n", "\n").replace("\r", "\n")
    normalized = re.sub(r"[\t\f\v ]+", " ", normalized)
    normalized = re.sub(r" *\n *", "\n", normalized)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    return normalized.strip()


def _truncate(value: str) -> EmailBodyPreview:
    if len(value) <= MAX_BODY_CHARACTERS:
        return EmailBodyPreview(text=value, truncated=False)
    return EmailBodyPreview(
        text=value[:MAX_BODY_CHARACTERS].rstrip(),
        truncated=True,
    )
