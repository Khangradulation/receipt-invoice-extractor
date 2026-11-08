from fastapi.testclient import TestClient

from receipt_shared.config import Environment, Settings
from receipt_worker.main import create_app


def test_health_ok() -> None:
    client = TestClient(create_app(Settings(_env_file=None)))
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["service"] == "worker"


def test_docs_disabled_outside_local() -> None:
    client = TestClient(create_app(Settings(_env_file=None, environment=Environment.PROD)))
    assert client.get("/docs").status_code == 404
