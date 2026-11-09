"""Document records: one Firestore document per uploaded file (``documents/{document_id}``).

Phase 4 creates the record when an upload URL is issued. Later phases add processing fields
(extraction, validation, history), which is why the model allows extra keys to round-trip.
"""

from __future__ import annotations

import threading
from datetime import UTC, datetime
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field

from receipt_shared.models.enums import DocumentStatus


def _now() -> datetime:
    return datetime.now(UTC)


class DocumentRecord(BaseModel):
    model_config = ConfigDict(extra="allow")

    document_id: str
    user_id: str
    status: DocumentStatus
    original_filename: str
    bucket: str
    object_name: str
    content_type: str
    size_bytes: int
    client_sha256: str | None = None
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)
    upload_url_expires_at: datetime | None = None

    def to_firestore(self) -> dict[str, Any]:
        return self.model_dump(mode="python")

    @classmethod
    def from_firestore(cls, data: dict[str, Any]) -> DocumentRecord:
        return cls.model_validate(data)


class DocumentAlreadyExistsError(RuntimeError):
    pass


class DocumentRepository(Protocol):
    def create(self, record: DocumentRecord) -> None:
        """Insert a new record; raise ``DocumentAlreadyExistsError`` if the id is taken."""
        ...

    def get(self, document_id: str) -> DocumentRecord | None: ...


class InMemoryDocumentRepository:
    def __init__(self) -> None:
        self._items: dict[str, DocumentRecord] = {}
        self._lock = threading.Lock()

    def create(self, record: DocumentRecord) -> None:
        with self._lock:
            if record.document_id in self._items:
                raise DocumentAlreadyExistsError(record.document_id)
            self._items[record.document_id] = record.model_copy(deep=True)

    def get(self, document_id: str) -> DocumentRecord | None:
        item = self._items.get(document_id)
        return item.model_copy(deep=True) if item else None


class FirestoreDocumentRepository:
    def __init__(self, client: Any, collection: str = "documents") -> None:
        self._collection = client.collection(collection)

    @classmethod
    def from_settings(cls, settings: Any) -> FirestoreDocumentRepository:
        from google.cloud import firestore

        client = firestore.Client(
            project=settings.gcp_project_id, database=settings.firestore_database
        )
        return cls(client, settings.firestore_documents_collection)

    def create(self, record: DocumentRecord) -> None:
        from google.api_core.exceptions import AlreadyExists

        try:
            self._collection.document(record.document_id).create(record.to_firestore())
        except AlreadyExists as exc:
            raise DocumentAlreadyExistsError(record.document_id) from exc

    def get(self, document_id: str) -> DocumentRecord | None:
        snapshot = self._collection.document(document_id).get()
        if not snapshot.exists:
            return None
        return DocumentRecord.from_firestore(snapshot.to_dict())
