import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

pytestmark = pytest.mark.anyio


async def test_live_health_check(app: FastAPI) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        response = await client.get("/api/v1/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": "0.1.0"}
    assert response.headers["X-Request-ID"]


async def test_ready_health_check_validates_database(app: FastAPI) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        response = await client.get("/api/v1/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready", "database": "ok"}


async def test_not_found_uses_unified_error_contract(app: FastAPI) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        response = await client.get("/api/v1/not-exists", headers={"X-Request-ID": "test-request"})

    assert response.status_code == 404
    assert response.headers["X-Request-ID"] == "test-request"
    assert response.json() == {
        "success": False,
        "error": {
            "code": "NOT_FOUND",
            "message": "请求的资源不存在",
            "details": None,
        },
        "request_id": "test-request",
    }
