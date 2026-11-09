"""Domain models shared across services."""

from receipt_shared.models.enums import (
    DocumentStatus,
    DocumentType,
    DuplicateStatus,
    ProcessingOutcome,
)
from receipt_shared.models.extraction import (
    ExpenseCategory,
    ExtractedDocument,
    ExtractionMetadata,
    ExtractionResult,
    LineItem,
    PaymentMethod,
)
from receipt_shared.models.health import HealthResponse
from receipt_shared.models.validation import (
    DocumentFingerprint,
    Severity,
    ValidationCode,
    ValidationIssue,
    ValidationResult,
)

__all__ = [
    "DocumentFingerprint",
    "DocumentStatus",
    "DocumentType",
    "DuplicateStatus",
    "ExpenseCategory",
    "ExtractedDocument",
    "ExtractionMetadata",
    "ExtractionResult",
    "HealthResponse",
    "LineItem",
    "PaymentMethod",
    "ProcessingOutcome",
    "Severity",
    "ValidationCode",
    "ValidationIssue",
    "ValidationResult",
]
