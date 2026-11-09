"""Validation result models.

A ``ValidationResult`` is persisted with every document (Firestore) so users can see exactly why
a record needs review. Issue messages may contain amounts and field values: they are shown to the
document's owner, but must never be written to application logs.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, Field

from receipt_shared.models.enums import DuplicateStatus, ProcessingOutcome


class Severity(StrEnum):
    ERROR = "error"  # blocks automatic acceptance -> REVIEW_REQUIRED
    WARNING = "warning"  # informational; the record can still be VALID


class ValidationCode(StrEnum):
    # Required / optional fields
    MISSING_REQUIRED_FIELD = "MISSING_REQUIRED_FIELD"
    MISSING_OPTIONAL_FIELD = "MISSING_OPTIONAL_FIELD"
    # Classification
    INVALID_DOCUMENT_TYPE = "INVALID_DOCUMENT_TYPE"
    UNSUPPORTED_CURRENCY = "UNSUPPORTED_CURRENCY"
    # Dates
    DATE_IN_FUTURE = "DATE_IN_FUTURE"
    DATE_TOO_OLD = "DATE_TOO_OLD"
    DUE_DATE_BEFORE_DOCUMENT_DATE = "DUE_DATE_BEFORE_DOCUMENT_DATE"
    # Amounts
    NEGATIVE_AMOUNT = "NEGATIVE_AMOUNT"
    NEGATIVE_DISCOUNT = "NEGATIVE_DISCOUNT"
    ZERO_TOTAL = "ZERO_TOTAL"
    AMOUNT_TOO_LARGE = "AMOUNT_TOO_LARGE"
    TOO_MANY_DECIMALS = "TOO_MANY_DECIMALS"
    # Arithmetic
    TOTAL_MISMATCH = "TOTAL_MISMATCH"
    TOTALS_NOT_VERIFIABLE = "TOTALS_NOT_VERIFIABLE"
    TAX_INCLUDED_IN_SUBTOTAL = "TAX_INCLUDED_IN_SUBTOTAL"
    LINE_ITEMS_MISMATCH = "LINE_ITEMS_MISMATCH"
    LINE_ITEM_ARITHMETIC = "LINE_ITEM_ARITHMETIC"
    # Invoice specifics
    INVOICE_WITHOUT_NUMBER = "INVOICE_WITHOUT_NUMBER"
    # Duplicates
    DUPLICATE_FILE = "DUPLICATE_FILE"
    POSSIBLE_DUPLICATE = "POSSIBLE_DUPLICATE"
    # Carried over from extraction (e.g. an unparseable date set to null)
    EXTRACTION_WARNING = "EXTRACTION_WARNING"
    # Processing
    PROCESSING_FAILED = "PROCESSING_FAILED"


class ValidationIssue(BaseModel):
    code: ValidationCode
    severity: Severity
    message: str
    fields: list[str] = Field(default_factory=list)


class ValidationResult(BaseModel):
    is_valid: bool
    validation_status: ProcessingOutcome
    validation_errors: list[ValidationIssue] = Field(default_factory=list)
    validation_warnings: list[ValidationIssue] = Field(default_factory=list)
    failed_fields: list[str] = Field(default_factory=list)
    duplicate_status: DuplicateStatus = DuplicateStatus.NOT_DUPLICATE
    duplicate_of: list[str] = Field(
        default_factory=list, description="document_ids of the matching earlier documents"
    )
    rules_version: str

    @classmethod
    def processing_failed(cls, reason: str, *, rules_version: str) -> ValidationResult:
        """Result for a document whose extraction failed permanently (kept, never discarded)."""
        issue = ValidationIssue(
            code=ValidationCode.PROCESSING_FAILED, severity=Severity.ERROR, message=reason
        )
        return cls(
            is_valid=False,
            validation_status=ProcessingOutcome.PROCESSING_FAILED,
            validation_errors=[issue],
            rules_version=rules_version,
        )


class DocumentFingerprint(BaseModel):
    """The identifying facts of a stored document, used for duplicate detection."""

    document_id: str
    user_id: str
    file_sha256: str
    merchant_key: str | None = None
    document_number_key: str | None = None
    document_date: date | None = None
    total_amount: Decimal | None = None
    currency: str | None = None
    status: str
    created_at: datetime
