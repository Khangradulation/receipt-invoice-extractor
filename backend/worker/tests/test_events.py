import json

import pytest

from receipt_worker.events import FINALIZED, InvalidEventError, parse_storage_event

DATA = {
    "bucket": "docs-bucket",
    "name": "uploads/u/d/a.pdf",
    "generation": "1794259580713424",
    "size": "53370",
    "contentType": "application/pdf",
}
HEADERS = {
    "ce-id": "123",
    "ce-type": FINALIZED,
    "ce-source": "//storage.googleapis.com/projects/_/buckets/docs-bucket",
    "ce-specversion": "1.0",
    "Content-Type": "application/json",
}


def test_binary_mode() -> None:
    event = parse_storage_event(HEADERS, json.dumps(DATA).encode())
    assert event.id == "123"
    assert event.type == FINALIZED
    assert event.bucket == "docs-bucket"
    assert event.name == "uploads/u/d/a.pdf"
    assert event.generation == 1794259580713424
    assert event.size == 53370
    assert event.content_type == "application/pdf"


def test_header_names_are_case_insensitive() -> None:
    headers = {k.upper(): v for k, v in HEADERS.items()}
    assert parse_storage_event(headers, json.dumps(DATA).encode()).id == "123"


def test_structured_mode() -> None:
    body = {"specversion": "1.0", "id": "9", "type": FINALIZED, "source": "s", "data": DATA}
    event = parse_storage_event(
        {"content-type": "application/cloudevents+json; charset=utf-8"}, json.dumps(body).encode()
    )
    assert (event.id, event.generation) == ("9", 1794259580713424)


@pytest.mark.parametrize(
    ("headers", "body"),
    [
        (HEADERS, b"not json"),
        ({k: v for k, v in HEADERS.items() if k != "ce-id"}, json.dumps(DATA).encode()),
        (HEADERS, json.dumps({**DATA, "generation": None}).encode()),
        (HEADERS, json.dumps({**DATA, "generation": "abc"}).encode()),
        (HEADERS, json.dumps({k: v for k, v in DATA.items() if k != "name"}).encode()),
        (HEADERS, b"[]"),
        (
            {"content-type": "application/cloudevents+json"},
            b'{"id":"1","type":"t","source":"s","data":"x"}',
        ),
    ],
)
def test_malformed_events_rejected(headers: dict[str, str], body: bytes) -> None:
    with pytest.raises(InvalidEventError):
        parse_storage_event(headers, body)
