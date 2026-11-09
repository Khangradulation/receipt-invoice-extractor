"""Build the BigQuery rows for one document (pure functions, no I/O).

* ``documents`` and ``extraction_metrics`` get a row for every processed document.
* ``extracted_transactions`` and ``line_items`` only get rows for VALID or APPROVED documents;
  for any other status they are explicitly cleared, so they never hold unvalidated data.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from receipt_shared.models.enums import DocumentStatus, ProcessingOutcome
from receipt_shared.models.extraction import ExtractedDocument, ExtractionResult
from receipt_shared.models.validation import ValidationResult
from receipt_shared.repository import DocumentRecord

APPROVED_STATUSES = frozenset({DocumentStatus.VALID, DocumentStatus.APPROVED})


def _json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, datetime):
        aware = value if value.tzinfo else value.replace(tzinfo=UTC)
        return aware.astimezone(UTC).isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if hasattr(value, "value") and isinstance(getattr(value, "value", None), str):
        return value.value  # enums
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    return value


def _clean(row: dict[str, Any]) -> dict[str, Any]:
    return {k: _json_safe(v) for k, v in row.items()}


@dataclass(frozen=True)
class AnalyticsRows:
    document_id: str
    document: dict[str, Any]
    metrics: dict[str, Any] | None = None
    transaction: dict[str, Any] | None = None
    line_items: list[dict[str, Any]] = field(default_factory=list)


def build_rows(
    record: DocumentRecord,
    *,
    status: DocumentStatus,
    extraction: ExtractionResult | None,
    validation: ValidationResult | None,
    now: datetime,
    effective_document: ExtractedDocument | None = None,
    record_source: str = "AI",
    approved_by: str | None = None,
    approved_at: datetime | None = None,
    review_required: bool | None = None,
) -> AnalyticsRows:
    """Rows for ``record`` in its new ``status``.

    ``effective_document`` is the data to publish: the AI extraction by default, or the
    reviewer-corrected document for APPROVED records (Phase 9).
    """
    doc = effective_document or (extraction.document if extraction else None)
    error_code = (record.last_error or {}).get("code") if status is DocumentStatus.FAILED else None
    if review_required is None:
        review_required = bool(
            validation and validation.validation_status is ProcessingOutcome.REVIEW_REQUIRED
        )

    document_row = _clean(
        {
            "document_id": record.document_id,
            "user_id": record.user_id,
            "document_type": doc.document_type if doc else None,
            "processing_status": status,
            "validation_status": validation.validation_status if validation else None,
            "review_required": review_required,
            "duplicate_status": validation.duplicate_status if validation else None,
            "error_count": len(validation.validation_errors) if validation else None,
            "warning_count": len(validation.validation_warnings) if validation else None,
            "failed_fields": list(validation.failed_fields) if validation else [],
            "error_code": error_code,
            "content_type": record.content_type,
            "size_bytes": record.size_bytes,
            "page_count": record.page_count,
            "model_version": extraction.metadata.model_version if extraction else None,
            "prompt_version": extraction.metadata.prompt_version if extraction else None,
            "rules_version": validation.rules_version if validation else None,
            "processing_attempts": record.processing_attempts,
            "processing_duration_ms": record.processing_duration_ms,
            "created_at": record.created_at,
            "uploaded_at": record.uploaded_at,
            "completed_at": record.completed_at or now,
            "loaded_at": now,
        }
    )

    metrics_row = None
    if extraction is not None:
        md = extraction.metadata
        metrics_row = _clean(
            {
                "metric_id": f"{record.document_id}:{record.object_generation or 0}",
                "document_id": record.document_id,
                "user_id": record.user_id,
                "evaluation_run_id": None,
                "model": md.model,
                "model_version": md.model_version,
                "prompt_version": md.prompt_version,
                "location": md.location,
                "mime_type": record.content_type,
                "page_count": record.page_count,
                "latency_ms": md.latency_ms,
                "gemini_attempts": md.attempts,
                "prompt_tokens": md.prompt_tokens,
                "output_tokens": md.output_tokens,
                "thoughts_tokens": md.thoughts_tokens,
                "total_tokens": md.total_tokens,
                "outcome": status,
                "missing_field_count": len(extraction.document.missing_fields),
                "extraction_warning_count": len(extraction.warnings),
                "fields_compared": None,
                "fields_correct": None,
                "processed_at": record.extracted_at or now,
            }
        )

    transaction_row = None
    line_rows: list[dict[str, Any]] = []
    if status in APPROVED_STATUSES and doc is not None:
        transaction_row = _clean(
            {
                "document_id": record.document_id,
                "user_id": record.user_id,
                "document_type": doc.document_type,
                "merchant_name": doc.merchant_name,
                "merchant_address": doc.merchant_address,
                "document_date": doc.document_date,
                "due_date": doc.due_date,
                "document_number": doc.document_number,
                "currency": doc.currency,
                "subtotal": doc.subtotal,
                "tax_amount": doc.tax_amount,
                "discount_amount": doc.discount_amount,
                "total_amount": doc.total_amount,
                "expense_category": doc.expense_category,
                "payment_method": doc.payment_method,
                "processing_status": status,
                "record_source": record_source,
                "model_version": extraction.metadata.model_version if extraction else None,
                "approved_by": approved_by,
                "approved_at": approved_at,
                "created_at": record.created_at,
                "loaded_at": now,
            }
        )
        line_rows = [
            _clean(
                {
                    "document_id": record.document_id,
                    "user_id": record.user_id,
                    "line_number": i,
                    "description": item.description,
                    "quantity": item.quantity,
                    "unit_price": item.unit_price,
                    "total_price": item.total_price,
                    "currency": doc.currency,
                    "document_date": doc.document_date,
                    "loaded_at": now,
                }
            )
            for i, item in enumerate(doc.line_items, start=1)
        ]

    return AnalyticsRows(
        document_id=record.document_id,
        document=document_row,
        metrics=metrics_row,
        transaction=transaction_row,
        line_items=line_rows,
    )
