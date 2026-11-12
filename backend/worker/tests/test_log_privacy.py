"""Logs carry IDs, statuses and timings only: never receipt contents or filenames (Phase 14)."""

import logging
from decimal import Decimal

import pytest

from receipt_shared.extraction.errors import ModelResponseError
from receipt_shared.logging import JsonFormatter

from .conftest import Env, good_document

SENSITIVE = [
    "Maple Leaf Cafe",  # merchant name
    "42 Harbour St",  # merchant address
    "26.68",  # total
    "99.00",  # the altered total in the review case
    "receipt.png",  # original filename / object name
]


def _logged(caplog: pytest.LogCaptureFixture) -> str:
    formatter = JsonFormatter("worker")
    return "\n".join(formatter.format(r) for r in caplog.records)


def test_worker_logs_never_contain_receipt_contents(
    env: Env, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    _, event = env.upload()
    env.processor.handle(event)  # valid
    env.extractor.default = good_document(total_amount=Decimal("99.00"))
    _, event = env.upload()
    env.processor.handle(event)  # review required
    env.extractor.outcomes = [ModelResponseError("unusable answer")]
    _, event = env.upload()
    env.processor.handle(event)  # failed

    logs = _logged(caplog)
    assert "processing completed" in logs  # the logs were captured
    assert '"document_id"' in logs
    for value in SENSITIVE:
        assert value not in logs, f"{value!r} leaked into logs"
