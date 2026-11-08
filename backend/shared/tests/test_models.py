import itertools
import json
import logging

from receipt_shared.logging import JsonFormatter
from receipt_shared.models import DocumentStatus
from receipt_shared.models.enums import ALLOWED_TRANSITIONS, can_transition


def test_every_status_has_transition_entry() -> None:
    assert set(ALLOWED_TRANSITIONS) == set(DocumentStatus)


def test_happy_path_transitions() -> None:
    path = [
        DocumentStatus.UPLOADED,
        DocumentStatus.PROCESSING,
        DocumentStatus.EXTRACTED,
        DocumentStatus.VALIDATING,
        DocumentStatus.REVIEW_REQUIRED,
        DocumentStatus.APPROVED,
    ]
    for current, nxt in itertools.pairwise(path):
        assert can_transition(current, nxt)


def test_terminal_states_cannot_move() -> None:
    assert not can_transition(DocumentStatus.VALID, DocumentStatus.PROCESSING)
    assert not can_transition(DocumentStatus.APPROVED, DocumentStatus.REVIEW_REQUIRED)
    assert DocumentStatus.REJECTED.is_terminal


def test_json_formatter_includes_extra_fields() -> None:
    record = logging.LogRecord("t", logging.INFO, __file__, 1, "processed %s", ("doc",), None)
    record.document_id = "abc123"
    out = json.loads(JsonFormatter("svc").format(record))
    assert out["severity"] == "INFO"
    assert out["message"] == "processed doc"
    assert out["document_id"] == "abc123"
    assert out["service"] == "svc"


def test_configure_logging_disables_uvicorn_access_log() -> None:
    from receipt_shared.logging import configure_logging

    configure_logging("svc", "INFO")
    access = logging.getLogger("uvicorn.access")
    assert access.disabled
    assert not access.hasHandlers()
