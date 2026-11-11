from fastapi.testclient import TestClient

from receipt_api.main import create_app
from receipt_shared.config import Settings


def _client() -> TestClient:
    return TestClient(create_app(Settings(_env_file=None)))


def test_health_ok() -> None:
    resp = _client().get("/api/v1/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["service"] == "api"
    assert body["version"] == "0.1.0"
    assert resp.headers["X-Request-ID"]


def test_request_id_is_propagated() -> None:
    resp = _client().get("/api/v1/health", headers={"X-Request-ID": "req-123"})
    assert resp.headers["X-Request-ID"] == "req-123"


def test_unknown_route_uses_error_model() -> None:
    resp = _client().get("/api/v1/does-not-exist", headers={"X-Request-ID": "r1"})
    assert resp.status_code == 404
    assert resp.json() == {
        "error": {"code": "not_found", "message": "Not Found", "request_id": "r1"}
    }


def test_cors_allows_configured_origin() -> None:
    resp = _client().options(
        "/api/v1/health",
        headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "GET"},
    )
    assert resp.headers.get("access-control-allow-origin") == "http://localhost:5173"


def test_cors_rejects_other_origin() -> None:
    resp = _client().get("/api/v1/health", headers={"Origin": "https://evil.test"})
    assert "access-control-allow-origin" not in resp.headers


def test_openapi_docs_served() -> None:
    resp = _client().get("/api/v1/openapi.json")
    assert resp.status_code == 200
    assert "/api/v1/health" in resp.json()["paths"]


def test_security_headers_on_every_response() -> None:
    client = _client()
    for resp in (client.get("/api/v1/health"), client.get("/api/v1/does-not-exist")):
        assert resp.headers["Strict-Transport-Security"].startswith("max-age=31536000")
        assert resp.headers["X-Content-Type-Options"] == "nosniff"
        assert resp.headers["X-Frame-Options"] == "DENY"
        assert resp.headers["Cache-Control"] == "no-store"
        assert (
            resp.headers["Content-Security-Policy"] == "default-src 'none'; frame-ancestors 'none'"
        )


def test_docs_pages_are_not_blocked_by_csp() -> None:
    resp = _client().get("/api/v1/docs")
    assert resp.status_code == 200
    assert "Content-Security-Policy" not in resp.headers


def test_unsafe_request_ids_are_replaced() -> None:
    for bad in ["a" * 200, "x\nInjected: 1", "<script>", "a b"]:
        resp = _client().get("/api/v1/health", headers={"X-Request-ID": bad})
        assert resp.headers["X-Request-ID"] != bad
        assert len(resp.headers["X-Request-ID"]) == 32
