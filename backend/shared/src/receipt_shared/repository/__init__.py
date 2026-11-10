"""Persistence of operational document state (Firestore in production)."""

from receipt_shared.repository.documents import (
    Claim,
    ClaimOutcome,
    DocumentAlreadyExistsError,
    DocumentRecord,
    DocumentRepository,
    FirestoreDocumentRepository,
    InMemoryDocumentRepository,
    InvalidCursorError,
    Page,
    RepositoryDuplicateIndex,
    decide_claim,
    history_entry,
)

__all__ = [
    "Claim",
    "ClaimOutcome",
    "DocumentAlreadyExistsError",
    "DocumentRecord",
    "DocumentRepository",
    "FirestoreDocumentRepository",
    "InMemoryDocumentRepository",
    "InvalidCursorError",
    "Page",
    "RepositoryDuplicateIndex",
    "decide_claim",
    "history_entry",
]
