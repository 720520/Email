from fastapi import FastAPI
from fastapi.testclient import TestClient


def test_live_health_check(app: FastAPI) -> None:
    with TestClient(app) as client:
        response = client.get("/api/v1/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": "0.1.0"}
    assert response.headers["X-Request-ID"]


def test_ready_health_check_validates_database(app: FastAPI) -> None:
    with TestClient(app) as client:
        response = client.get("/api/v1/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready", "database": "ok"}


def test_not_found_uses_unified_error_contract(app: FastAPI) -> None:
    with TestClient(app) as client:
        response = client.get("/api/v1/not-exists", headers={"X-Request-ID": "test-request"})

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

