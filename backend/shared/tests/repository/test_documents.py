from datetime import UTC, datetime
from typing import Any

import pytest
from google.api_core.exceptions import AlreadyExists

from receipt_shared.models.enums import DocumentStatus
from receipt_shared.repository import (
    DocumentAlreadyExistsError,
    DocumentRecord,
    FirestoreDocumentRepository,
    InMemoryDocumentRepository,
)


def record(doc_id: str = "d1") -> DocumentRecord:
    return DocumentRecord(
        document_id=doc_id,
        user_id="u1",
        status=DocumentStatus.AWAITING_UPLOAD,
        original_filename="a.pdf",
        bucket="b",
        object_name=f"uploads/u1/{doc_id}/a.pdf",
        content_type="application/pdf",
        size_bytes=100,
        created_at=datetime(2026, 11, 9, tzinfo=UTC),
        updated_at=datetime(2026, 11, 9, tzinfo=UTC),
    )


def test_in_memory_create_get() -> None:
    repo = InMemoryDocumentRepository()
    repo.create(record())
    got = repo.get("d1")
    assert got is not None
    assert got.status is DocumentStatus.AWAITING_UPLOAD
    assert repo.get("missing") is None


def test_in_memory_rejects_duplicate_ids() -> None:
    repo = InMemoryDocumentRepository()
    repo.create(record())
    with pytest.raises(DocumentAlreadyExistsError):
        repo.create(record())


def test_firestore_round_trip_keeps_extra_fields() -> None:
    data = record().to_firestore() | {"review": {"corrections": []}}
    back = DocumentRecord.from_firestore(data)
    assert back.model_extra == {"review": {"corrections": []}}
    assert back.created_at == datetime(2026, 11, 9, tzinfo=UTC)


class _Snap:
    def __init__(self, data: dict[str, Any] | None) -> None:
        self.exists = data is not None
        self._data = data

    def to_dict(self) -> dict[str, Any] | None:
        return self._data


class _Doc:
    def __init__(self, store: dict[str, dict[str, Any]], key: str) -> None:
        self.store, self.key = store, key

    def create(self, data: dict[str, Any]) -> None:
        if self.key in self.store:
            raise AlreadyExists("exists")
        self.store[self.key] = data

    def get(self) -> _Snap:
        return _Snap(self.store.get(self.key))

    def delete(self) -> None:
        self.store.pop(self.key, None)


class _Collection:
    def __init__(self) -> None:
        self.store: dict[str, dict[str, Any]] = {}

    def document(self, key: str) -> _Doc:
        return _Doc(self.store, key)


class _Client:
    def __init__(self) -> None:
        self.col = _Collection()
        self.collection_name: str | None = None

    def collection(self, name: str) -> _Collection:
        self.collection_name = name
        return self.col


def test_firestore_repository_with_fake_client() -> None:
    client = _Client()
    repo = FirestoreDocumentRepository(client, "documents")
    repo.create(record())
    assert client.collection_name == "documents"
    assert client.col.store["d1"]["status"] is DocumentStatus.AWAITING_UPLOAD
    got = repo.get("d1")
    assert got is not None
    assert got.user_id == "u1"
    assert repo.get("nope") is None
    with pytest.raises(DocumentAlreadyExistsError):
        repo.create(record())


def test_update_if_unchanged_detects_concurrent_writes() -> None:
    from receipt_shared.repository import ConcurrentModificationError

    repo = InMemoryDocumentRepository()
    repo.create(record())
    current = repo.get("d1")
    assert current is not None
    repo.update_if_unchanged("d1", current.updated_at, {"x": 1})
    with pytest.raises(ConcurrentModificationError):
        repo.update_if_unchanged("d1", current.updated_at, {"x": 2})  # stale timestamp
    with pytest.raises(ConcurrentModificationError):
        repo.update_if_unchanged("missing", current.updated_at, {"x": 3})
    latest = repo.get("d1")
    assert latest is not None
    assert (latest.model_extra or {})["x"] == 1


def test_delete_removes_the_record_and_is_idempotent() -> None:
    for repo in (InMemoryDocumentRepository(), FirestoreDocumentRepository(_Client(), "documents")):
        repo.create(record())
        repo.delete("d1")
        assert repo.get("d1") is None
        repo.delete("d1")  # no error the second time
