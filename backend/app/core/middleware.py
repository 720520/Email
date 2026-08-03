"""请求链路标识与访问日志中间件。"""

from __future__ import annotations

import logging
import time
from uuid import uuid4

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.context import bind_request_id, reset_request_id

logger = logging.getLogger(__name__)


class RequestContextMiddleware:
    """纯 ASGI 中间件，避免 BaseHTTPMiddleware 的流式响应限制。"""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        incoming_headers = dict(scope.get("headers", []))
        request_id = incoming_headers.get(b"x-request-id", b"").decode("utf-8", "ignore")
        request_id = request_id.strip()[:128] or uuid4().hex
        scope.setdefault("state", {})["request_id"] = request_id
        token = bind_request_id(request_id)
        started_at = time.perf_counter()
        status_code = 500

        async def send_with_request_id(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                headers = MutableHeaders(scope=message)
                headers["X-Request-ID"] = request_id
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        finally:
            duration_ms = round((time.perf_counter() - started_at) * 1000, 2)
            logger.info(
                "HTTP 请求完成",
                extra={
                    "method": scope["method"],
                    "path": scope["path"],
                    "status_code": status_code,
                    "duration_ms": duration_ms,
                },
            )
            reset_request_id(token)

