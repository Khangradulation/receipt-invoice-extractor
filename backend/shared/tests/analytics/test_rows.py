from datetime import UTC, date, datetime
from decimal import Decimal

from receipt_shared.analytics.rows import build_rows
from receipt_shared.models.enums import DocumentStatus, DuplicateStatus, ProcessingOutcome
from receipt_shared.models.extraction import (
    ExtractedDocument,
    ExtractionMetadata,
    ExtractionResult,
    LineItem,
)
from receipt_shared.models.validation import (
    Severity,
    ValidationCode,
    ValidationIssue,
    ValidationResult,
)
from receipt_shared.repository import DocumentRecord

NOW = datetime(2026, 11, 9, 22, 0, tzinfo=UTC)


def record(**overrides: object) -> DocumentRecord:
    base: dict[str, object] = {
        "document_id": "d1",
        "user_id": "u1",
        "status": DocumentStatus.VALIDATING,
        "original_filename": "r.pdf",
        "bucket": "b",
        "object_name": "uploads/u1/d1/r.pdf",
        "content_type": "application/pdf",
        "size_bytes": 1000,
        "page_count": 1,
        "object_generation": 77,
        "processing_attempts": 1,
        "processing_duration_ms": 5400.0,
        "created_at": datetime(2026, 11, 9, 21, 0, tzinfo=UTC),
        "extracted_at": datetime(2026, 11, 9, 21, 0, 5, tzinfo=UTC),
    }
    return DocumentRecord(**(base | overrides))


def extraction(**doc_overrides: object) -> ExtractionResult:
    doc: dict[str, object] = {
        "document_type": "receipt",
        "merchant_name": "Maple Leaf Cafe",
        "document_date": date(2026, 3, 14),
        "currency": "CAD",
        "subtotal": Decimal("23.20"),
        "tax_amount": Decimal("3.48"),
        "total_amount": Decimal("26.68"),
        "expense_category": "meals",
        "line_items": [
            LineItem(
                description="Latte",
                quantity=Decimal("2"),
                unit_price=Decimal("5.25"),
                total_price=Decimal("10.50"),
            ),
            LineItem(description="Sandwich", total_price=Decimal("12.70")),
        ],
    }
    return ExtractionResult(
        document=ExtractedDocument(**(doc | doc_overrides)),
        metadata=ExtractionMetadata(
            model="gemini-3.8-flash",
            model_version="gemini-3.8-flash",
            prompt_version="p1",
            location="global",
            latency_ms=4600.0,
            attempts=1,
            prompt_tokens=2800,
            output_tokens=230,
            total_tokens=3030,
        ),
        warnings=["w1"],
    )


def validation(status: ProcessingOutcome = ProcessingOutcome.VALID) -> ValidationResult:
    errors = (
        [
            ValidationIssue(
                code=ValidationCode.TOTAL_MISMATCH,
                severity=Severity.ERROR,
                message="m",
                fields=["total_amount"],
            )
        ]
        if status is ProcessingOutcome.REVIEW_REQUIRED
        else []
    )
    return ValidationResult(
        is_valid=status is ProcessingOutcome.VALID,
        validation_status=status,
        validation_errors=errors,
        failed_fields=["total_amount"] if errors else [],
        duplicate_status=DuplicateStatus.NOT_DUPLICATE,
        rules_version="r1",
    )


def test_valid_document_produces_transaction_and_line_items() -> None:
    rows = build_rows(
        record(),
        status=DocumentStatus.VALID,
        extraction=extraction(),
        validation=validation(),
        now=NOW,
    )
    assert rows.transaction is not None
    tx = rows.transaction
    assert tx["total_amount"] == "26.68"  # exact decimal string, not a float
    assert tx["subtotal"] == "23.20"
    assert tx["document_date"] == "2026-03-14"
    assert tx["record_source"] == "AI"
    assert tx["processing_status"] == "VALID"
    assert tx["created_at"] == "2026-11-09T21:00:00+00:00"
    assert [li["line_number"] for li in rows.line_items] == [1, 2]
    assert rows.line_items[0]["total_price"] == "10.50"
    assert rows.line_items[1]["quantity"] is None  # not printed -> null, never 0
    assert all(li["document_id"] == "d1" and li["currency"] == "CAD" for li in rows.line_items)


def test_review_required_document_has_no_transaction() -> None:
    rows = build_rows(
        record(), status=DocumentStatus.REVIEW_REQUIRED, extraction=extraction(),
        validation=validation(ProcessingOutcome.REVIEW_REQUIRED), now=NOW,
    )  # fmt: skip
    assert rows.transaction is None
    assert rows.line_items == []
    assert rows.document["processing_status"] == "REVIEW_REQUIRED"
    assert rows.document["review_required"] is True
    assert rows.document["failed_fields"] == ["total_amount"]
    assert rows.document["error_count"] == 1


def test_duplicate_has_no_transaction() -> None:
    v = validation().model_copy(update={"validation_status": ProcessingOutcome.DUPLICATE})
    rows = build_rows(
        record(), status=DocumentStatus.DUPLICATE, extraction=extraction(), validation=v, now=NOW
    )
    assert rows.transaction is None


def test_failed_document_records_error_code_without_metrics() -> None:
    rows = build_rows(
        record(last_error={"code": "integrity_check_failed"}), status=DocumentStatus.FAILED,
        extraction=None, validation=None, now=NOW,
    )  # fmt: skip
    assert rows.document["error_code"] == "integrity_check_failed"
    assert rows.metrics is None
    assert rows.transaction is None


def test_metrics_row() -> None:
    rows = build_rows(
        record(),
        status=DocumentStatus.VALID,
        extraction=extraction(),
        validation=validation(),
        now=NOW,
    )
    m = rows.metrics
    assert m is not None
    assert m["metric_id"] == "d1:77"
    assert (m["latency_ms"], m["total_tokens"], m["outcome"]) == (4600.0, 3030, "VALID")
    assert m["extraction_warning_count"] == 1
    assert m["processed_at"] == "2026-11-09T21:00:05+00:00"


def test_approved_uses_corrected_document() -> None:
    corrected = extraction(total_amount=Decimal("27.00")).document
    rows = build_rows(
        record(), status=DocumentStatus.APPROVED, extraction=extraction(), validation=validation(),
        now=NOW, effective_document=corrected, record_source="REVIEWED", approved_by="u1",
        approved_at=NOW, review_required=True,
    )  # fmt: skip
    assert rows.transaction is not None
    assert rows.transaction["total_amount"] == "27.00"
    assert rows.transaction["record_source"] == "REVIEWED"
    assert rows.transaction["approved_at"] == "2026-11-09T22:00:00+00:00"
    assert rows.document["review_required"] is True
