"""Persistence of operational document state (Firestore in production)."""

from receipt_shared.repository.documents import (
    DocumentAlreadyExistsError,
    DocumentRecord,
    DocumentRepository,
    FirestoreDocumentRepository,
    InMemoryDocumentRepository,
)

__all__ = [
    "DocumentAlreadyExistsError",
    "DocumentRecord",
    "DocumentRepository",
    "FirestoreDocumentRepository",
    "InMemoryDocumentRepository",
]
