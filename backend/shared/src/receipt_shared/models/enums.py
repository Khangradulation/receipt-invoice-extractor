"""Enumerations describing the document lifecycle."""

from __future__ import annotations

from enum import StrEnum


class DocumentType(StrEnum):
    RECEIPT = "receipt"
    INVOICE = "invoice"


class DocumentStatus(StrEnum):
    """Operational state of a document, stored in Firestore."""

    AWAITING_UPLOAD = "AWAITING_UPLOAD"  # upload URL issued; file not received yet
    UPLOADED = "UPLOADED"
    PROCESSING = "PROCESSING"
    EXTRACTED = "EXTRACTED"
    VALIDATING = "VALIDATING"
    VALID = "VALID"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    DUPLICATE = "DUPLICATE"  # the exact same file was uploaded before
    FAILED = "FAILED"

    @property
    def is_terminal(self) -> bool:
        return self in _TERMINAL


_TERMINAL = frozenset(
    {
        DocumentStatus.VALID,
        DocumentStatus.APPROVED,
        DocumentStatus.REJECTED,
        DocumentStatus.DUPLICATE,
        DocumentStatus.FAILED,
    }
)

# Statuses in which the worker is (or was, if it crashed) handling the document.
IN_PROGRESS_STATUSES = frozenset(
    {DocumentStatus.PROCESSING, DocumentStatus.EXTRACTED, DocumentStatus.VALIDATING}
)
# Statuses after which automatic processing is finished (human review may still follow).
PROCESSING_DONE_STATUSES = frozenset(
    {
        DocumentStatus.VALID,
        DocumentStatus.REVIEW_REQUIRED,
        DocumentStatus.DUPLICATE,
        DocumentStatus.APPROVED,
        DocumentStatus.REJECTED,
    }
)

# Allowed state transitions. REVIEW_REQUIRED is resolved by a human (APPROVED / REJECTED).
# PROCESSING/EXTRACTED/VALIDATING -> PROCESSING: re-claim after a crashed attempt (lease expired).
# FAILED -> PROCESSING: a new object generation is uploaded after a failure.
ALLOWED_TRANSITIONS: dict[DocumentStatus, frozenset[DocumentStatus]] = {
    DocumentStatus.AWAITING_UPLOAD: frozenset({DocumentStatus.UPLOADED, DocumentStatus.FAILED}),
    DocumentStatus.UPLOADED: frozenset({DocumentStatus.PROCESSING, DocumentStatus.FAILED}),
    DocumentStatus.PROCESSING: frozenset(
        {DocumentStatus.PROCESSING, DocumentStatus.EXTRACTED, DocumentStatus.FAILED}
    ),
    DocumentStatus.EXTRACTED: frozenset(
        {DocumentStatus.PROCESSING, DocumentStatus.VALIDATING, DocumentStatus.FAILED}
    ),
    DocumentStatus.VALIDATING: frozenset(
        {
            DocumentStatus.PROCESSING,
            DocumentStatus.VALID,
            DocumentStatus.REVIEW_REQUIRED,
            DocumentStatus.DUPLICATE,
            DocumentStatus.FAILED,
        }
    ),
    DocumentStatus.REVIEW_REQUIRED: frozenset({DocumentStatus.APPROVED, DocumentStatus.REJECTED}),
    DocumentStatus.DUPLICATE: frozenset({DocumentStatus.REJECTED}),
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
