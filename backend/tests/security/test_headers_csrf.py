from app.main import app
from fastapi.testclient import TestClient


def test_security_headers_and_locked_csp() -> None:
    response = TestClient(app).get("/api/v1/health")
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert "unsafe-inline" not in response.headers["content-security-policy"]


def test_browser_state_change_without_csrf_is_rejected() -> None:
    response = TestClient(app).post("/api/v1/auth/logout", headers={"Origin": "https://testserver"})
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "CSRF_FAILED"
