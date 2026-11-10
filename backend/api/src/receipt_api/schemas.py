"""API response and request models."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field

from receipt_shared.models.enums import DocumentStatus
from receipt_shared.models.extraction import ExtractedDocument, ExtractionMetadata
from receipt_shared.models.validation import ValidationResult
from receipt_shared.repository import DocumentRecord


class ErrorInfo(BaseModel):
    code: str
    message: str


class DocumentSummary(BaseModel):
    document_id: str
    filename: str
    status: DocumentStatus
    content_type: str
    document_type: str | None = None
    merchant_name: str | None = None
    document_date: date | None = None
    total_amount: str | None = None
    currency: str | None = None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None
    error: ErrorInfo | None = None


class DocumentPage(BaseModel):
    items: list[DocumentSummary]
    next_cursor: str | None = Field(
        default=None, description="Pass as `cursor` to get the next page; null on the last page"
    )


class DocumentStatusResponse(BaseModel):
    document_id: str
    status: DocumentStatus
    processing_attempts: int
    updated_at: datetime
    completed_at: datetime | None = None
    error: ErrorInfo | None = None


class HistoryEntry(BaseModel):
    status: str
    at: datetime
    detail: str | None = None


class ExtractionResponse(BaseModel):
    document_id: str
    document: ExtractedDocument = Field(description="Original Gemini output (never modified)")
    metadata: ExtractionMetadata
    warnings: list[str]


class DocumentDetail(DocumentSummary):
    size_bytes: int
    page_count: int | None = None
    processing_attempts: int
    model_version: str | None = None
    uploaded_at: datetime | None = None
    processing_started_at: datetime | None = None
    extracted_at: datetime | None = None
    processing_duration_ms: float | None = None
    extraction: ExtractedDocument | None = Field(default=None, description="Original AI output")
    corrected: ExtractedDocument | None = Field(
        default=None, description="Reviewer-corrected values (if any)"
    )
    validation: ValidationResult | None = None
    history: list[HistoryEntry] = Field(default_factory=list)


class FileUrlResponse(BaseModel):
    url: str
    expires_at: datetime
    content_type: str


class Correction(BaseModel):
    review_id: str
    field_name: str
    original_value: str | None
    previous_value: str | None
    corrected_value: str | None
    reviewer_id: str
    reviewed_at: datetime


class ReviewDetail(BaseModel):
    document: DocumentDetail
    original: ExtractedDocument | None
    current: ExtractedDocument | None = Field(
        description="Values to approve (corrected or original)"
    )
    validation: ValidationResult | None
    failed_fields: list[str]
    corrections: list[Correction]
    duplicate_acknowledged: bool
    can_approve: bool


class CorrectionRequest(BaseModel):
    fields: dict[str, Any] = Field(
        description='Field values to set, e.g. {"total_amount": "26.68", "currency": "CAD"}',
        examples=[{"total_amount": "26.68", "merchant_name": "Maple Leaf Cafe"}],
    )
    acknowledge_duplicate: bool = Field(
        default=False, description="Confirm a possible duplicate is a separate transaction"
    )


class RejectRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


class AnalyticsResponse(BaseModel):
    start_date: date
    end_date: date
    rows: list[dict[str, Any]]


class AnalyticsOverview(BaseModel):
    start_date: date
    end_date: date
    total_spending: list[dict[str, Any]]
    average_transaction_value: list[dict[str, Any]]
    document_type_counts: list[dict[str, Any]]
    processing_success_rate: dict[str, Any]
    manual_review_rate: dict[str, Any]


def _error(record: DocumentRecord) -> ErrorInfo | None:
    if record.status is not DocumentStatus.FAILED or not record.last_error:
        return None
    return ErrorInfo(
        code=str(record.last_error.get("code", "error")),
        message=str(record.last_error.get("message", "Processing failed.")),
    )


def summary(record: DocumentRecord, effective: ExtractedDocument | None) -> DocumentSummary:
    return DocumentSummary(
        document_id=record.document_id,
        filename=record.original_filename,
        status=record.status,
        content_type=record.content_type,
        document_type=effective.document_type if effective else None,
        merchant_name=effective.merchant_name if effective else None,
        document_date=effective.document_date if effective else None,
        total_amount=format(effective.total_amount, "f")
        if effective and effective.total_amount is not None
        else None,
        currency=effective.currency if effective else None,
        created_at=record.created_at,
        updated_at=record.updated_at,
        completed_at=record.completed_at,
        error=_error(record),
    )


def status_response(record: DocumentRecord) -> DocumentStatusResponse:
    return DocumentStatusResponse(
        document_id=record.document_id,
        status=record.status,
        processing_attempts=record.processing_attempts,
        updated_at=record.updated_at,
        completed_at=record.completed_at,
        error=_error(record),
    )
