"""Enumerations describing the document lifecycle."""

from __future__ import annotations

from enum import StrEnum


class DocumentType(StrEnum):
    RECEIPT = "receipt"
    INVOICE = "invoice"


class DocumentStatus(StrEnum):
    """Operational state of a document, stored in Firestore."""

    UPLOADED = "UPLOADED"
    PROCESSING = "PROCESSING"
    EXTRACTED = "EXTRACTED"
    VALIDATING = "VALIDATING"
    VALID = "VALID"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    FAILED = "FAILED"

    @property
    def is_terminal(self) -> bool:
        return self in _TERMINAL


_TERMINAL = frozenset(
    {DocumentStatus.VALID, DocumentStatus.APPROVED, DocumentStatus.REJECTED, DocumentStatus.FAILED}
)

# Allowed state transitions. REVIEW_REQUIRED is resolved by a human (APPROVED / REJECTED).
# FAILED -> PROCESSING allows an explicit reprocess of a new object generation.
ALLOWED_TRANSITIONS: dict[DocumentStatus, frozenset[DocumentStatus]] = {
    DocumentStatus.UPLOADED: frozenset({DocumentStatus.PROCESSING, DocumentStatus.FAILED}),
    DocumentStatus.PROCESSING: frozenset({DocumentStatus.EXTRACTED, DocumentStatus.FAILED}),
    DocumentStatus.EXTRACTED: frozenset({DocumentStatus.VALIDATING, DocumentStatus.FAILED}),
    DocumentStatus.VALIDATING: frozenset(
        {DocumentStatus.VALID, DocumentStatus.REVIEW_REQUIRED, DocumentStatus.FAILED}
    ),
    DocumentStatus.REVIEW_REQUIRED: frozenset({DocumentStatus.APPROVED, DocumentStatus.REJECTED}),
    DocumentStatus.VALID: frozenset(),
    DocumentStatus.APPROVED: frozenset(),
    DocumentStatus.REJECTED: frozenset(),
    DocumentStatus.FAILED: frozenset({DocumentStatus.PROCESSING}),
}


def can_transition(current: DocumentStatus, target: DocumentStatus) -> bool:
    return target in ALLOWED_TRANSITIONS[current]


class ProcessingOutcome(StrEnum):
    """Result of the validation step for one document."""

    VALID = "VALID"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    PROCESSING_FAILED = "PROCESSING_FAILED"
    DUPLICATE = "DUPLICATE"


class DuplicateStatus(StrEnum):
    NOT_DUPLICATE = "NOT_DUPLICATE"
    POSSIBLE_DUPLICATE = "POSSIBLE_DUPLICATE"
    DUPLICATE = "DUPLICATE"
