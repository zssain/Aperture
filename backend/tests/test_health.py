"""Health, readiness and correlation-id behaviour for the v1 API."""

import pytest
from app.core.config import settings
from app.main import CORRELATION_ID_HEADER, app
from fastapi.testclient import TestClient

client = TestClient(app)


def test_health_returns_ok() -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": settings.version}


def test_ready_returns_503_when_db_down(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _raise() -> None:
        raise RuntimeError("database unreachable")

    monkeypatch.setattr("app.api.router.check_db_ready", _raise)

    response = client.get("/api/v1/ready")
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "not_ready"
    assert "database unreachable" in body["reason"]


def test_supplied_correlation_id_is_echoed() -> None:
    response = client.get(
        "/api/v1/health",
        headers={CORRELATION_ID_HEADER: "test-correlation-123"},
    )
    assert response.headers[CORRELATION_ID_HEADER] == "test-correlation-123"


def test_missing_correlation_id_is_generated() -> None:
    response = client.get("/api/v1/health")
    generated = response.headers.get(CORRELATION_ID_HEADER)
    assert generated
    # A generated id is a UUID4 (36 chars with hyphens), never an empty string.
    assert len(generated) == 36
