"""ONLYOFFICE 编辑会话、JWT 和短期文件/回调令牌。"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.core.config import OnlyOfficeSettings


class OnlyOfficeTokenError(ValueError):
    pass


class OnlyOfficeUnavailableError(ConnectionError):
    pass


class OnlyOfficeService:
    def __init__(self, settings: OnlyOfficeSettings) -> None:
        self.settings = settings
        self.secret = settings.jwt_secret.get_secret_value().encode("utf-8")

    def ensure_ready(self) -> None:
        if not self.settings.enabled:
            raise OnlyOfficeUnavailableError("OnlyOffice 尚未启用")
        if len(self.secret) < 32:
            raise OnlyOfficeUnavailableError("OnlyOffice JWT 密钥未配置")
        try:
            request = Request(
                f"{self.settings.internal_url.rstrip('/')}/healthcheck",
                headers={"User-Agent": "fund-nav-onlyoffice-health/1.0"},
            )
            with urlopen(request, timeout=self.settings.request_timeout) as response:
                if response.status != 200:
                    raise OnlyOfficeUnavailableError("OnlyOffice 健康检查失败")
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            raise OnlyOfficeUnavailableError("OnlyOffice 服务暂不可用") from exc

    def create_file_token(self, *, tenant_id: int, run_id: int, version_id: int) -> str:
        expires_at = datetime.now(UTC) + timedelta(seconds=self.settings.file_token_ttl_seconds)
        return self._encode_jwt(
            {
                "purpose": "onlyoffice-file",
                "tenant_id": tenant_id,
                "run_id": run_id,
                "version_id": version_id,
                "exp": int(expires_at.timestamp()),
            }
        )

    def verify_file_token(self, token: str, *, now: datetime | None = None) -> dict[str, Any]:
        payload = self._decode_jwt(token)
        current = now or datetime.now(UTC)
        if payload.get("purpose") != "onlyoffice-file":
            raise OnlyOfficeTokenError("文件令牌用途无效")
        if int(payload.get("exp", 0)) <= int(current.timestamp()):
            raise OnlyOfficeTokenError("文件令牌已过期")
        return payload

    def create_callback_token(
        self,
        *,
        tenant_id: int,
        run_id: int,
        version_id: int,
        user_id: int,
        username: str,
    ) -> str:
        expires_at = datetime.now(UTC) + timedelta(hours=24)
        return self._encode_jwt(
            {
                "purpose": "onlyoffice-callback",
                "tenant_id": tenant_id,
                "run_id": run_id,
                "version_id": version_id,
                "user_id": user_id,
                "username": username,
                "exp": int(expires_at.timestamp()),
            }
        )

    def verify_callback_token(
        self, token: str, *, now: datetime | None = None
    ) -> dict[str, Any]:
        payload = self._decode_jwt(token)
        current = now or datetime.now(UTC)
        if payload.get("purpose") != "onlyoffice-callback":
            raise OnlyOfficeTokenError("回调令牌用途无效")
        if int(payload.get("exp", 0)) <= int(current.timestamp()):
            raise OnlyOfficeTokenError("回调令牌已过期")
        return payload

    def build_session(
        self,
        *,
        tenant_id: int,
        run_id: int,
        version_id: int,
        content_hash: str,
        filename: str,
        user_id: int,
        username: str,
        editable: bool,
    ) -> dict[str, Any]:
        file_token = self.create_file_token(
            tenant_id=tenant_id,
            run_id=run_id,
            version_id=version_id,
        )
        file_url = (
            f"{self.settings.callback_base_url.rstrip('/')}/api/v1/onlyoffice/files/{file_token}"
        )
        callback_token = self.create_callback_token(
            tenant_id=tenant_id,
            run_id=run_id,
            version_id=version_id,
            user_id=user_id,
            username=username,
        )
        callback_url = (
            f"{self.settings.callback_base_url.rstrip('/')}/api/v1/onlyoffice/callbacks/"
            f"{callback_token}"
        )
        config: dict[str, Any] = {
            "document": {
                "fileType": "pptx",
                "key": f"report-{version_id}-{content_hash[:24]}",
                "title": filename,
                "url": file_url,
                "permissions": {
                    "download": True,
                    "edit": editable,
                    "print": True,
                },
            },
            "documentType": "slide",
            "editorConfig": {
                "mode": "edit" if editable else "view",
                "lang": "zh-CN",
                "callbackUrl": callback_url,
                "user": {"id": str(user_id), "name": username},
                "customization": {
                    "autosave": True,
                    "compactHeader": False,
                    "forcesave": editable,
                    "zoom": -1,
                },
                "coEditing": {"mode": "fast", "change": True},
            },
            "type": "desktop",
        }
        config["token"] = self._encode_jwt(config)
        return {
            "api_url": (
                f"{self.settings.public_url.rstrip('/')}/web-apps/apps/api/documents/api.js"
            ),
            "config": config,
        }

    def build_view_session(self, **kwargs: Any) -> dict[str, Any]:
        """兼容既有调用；显式生成只读会话。"""
        return self.build_session(**kwargs, editable=False)

    def _encode_jwt(self, payload: dict[str, Any]) -> str:
        header = {"alg": "HS256", "typ": "JWT"}
        signing_input = ".".join(
            (
                _b64(json.dumps(header, separators=(",", ":")).encode()),
                _b64(
                    json.dumps(
                        payload,
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ).encode()
                ),
            )
        )
        signature = hmac.new(self.secret, signing_input.encode("ascii"), hashlib.sha256)
        return f"{signing_input}.{_b64(signature.digest())}"

    def _decode_jwt(self, token: str) -> dict[str, Any]:
        try:
            header_part, payload_part, signature_part = token.split(".", 2)
            signing_input = f"{header_part}.{payload_part}"
            expected = hmac.new(
                self.secret,
                signing_input.encode("ascii"),
                hashlib.sha256,
            ).digest()
            if not hmac.compare_digest(expected, _unb64(signature_part)):
                raise OnlyOfficeTokenError("文件令牌签名无效")
            header = json.loads(_unb64(header_part))
            if header.get("alg") != "HS256":
                raise OnlyOfficeTokenError("文件令牌算法无效")
            payload = json.loads(_unb64(payload_part))
            if not isinstance(payload, dict):
                raise OnlyOfficeTokenError("文件令牌载荷无效")
            return payload
        except OnlyOfficeTokenError:
            raise
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            raise OnlyOfficeTokenError("文件令牌格式无效") from exc


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _unb64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
