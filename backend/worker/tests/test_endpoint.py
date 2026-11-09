import json

from fastapi.testclient import TestClient

from receipt_shared.config import Settings
from receipt_shared.models.enums import DocumentStatus
from receipt_worker.events import FINALIZED, StorageObjectEvent
from receipt_worker.main import create_app
from receipt_worker.pipeline import Outcome


class FakeProcessor:
    def __init__(self, outcome: Outcome) -> None:
        self.outcome = outcome
        self.events: list[StorageObjectEvent] = []

    def handle(self, event: StorageObjectEvent) -> Outcome:
        self.events.append(event)
        return self.outcome


HEADERS = {"ce-id": "1", "ce-type": FINALIZED, "ce-source": "s", "content-type": "application/json"}
BODY = json.dumps({"bucket": "b", "name": "uploads/u/d/a.png", "generation": "5"})


def client(outcome: Outcome) -> tuple[TestClient, FakeProcessor]:
    app = create_app(Settings(_env_file=None))
    proc = FakeProcessor(outcome)
    app.state.processor = proc
    return TestClient(app), proc


def test_event_is_dispatched_and_status_passed_through() -> None:
    c, proc = client(Outcome(200, "processed", "d", DocumentStatus.VALID))
    resp = c.post("/events/storage", content=BODY, headers=HEADERS)
    assert resp.status_code == 200
    assert resp.json() == {"result": "processed", "document_id": "d", "status": "VALID"}
    assert proc.events[0].generation == 5


def test_retryable_outcome_returns_non_2xx() -> None:
    c, _ = client(Outcome(503, "retry", "d"))
    assert c.post("/events/storage", content=BODY, headers=HEADERS).status_code == 503


def test_malformed_event_is_acknowledged_and_not_processed() -> None:
    c, proc = client(Outcome(200, "processed"))
    resp = c.post("/events/storage", content=b"garbage", headers=HEADERS)
    assert resp.status_code == 200
    assert resp.json() == {"result": "malformed_event"}
    assert proc.events == []
