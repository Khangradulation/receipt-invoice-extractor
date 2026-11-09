"""Live BigQuery: idempotent writes, approved-only transactions, and every analytics query.

make test-bigquery-live      (RUN_GCP_INTEGRATION=1; uses your ADC; rows are deleted after)
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

import pytest

from receipt_shared.config import Settings

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("RUN_GCP_INTEGRATION") != "1", reason="set RUN_GCP_INTEGRATION=1"
    ),
]


@pytest.fixture(scope="module")
def bq() -> Iterator[dict[str, Any]]:
    from google.cloud import bigquery

    from receipt_shared.analytics import (
        AnalyticsQueries,
        BigQueryAnalyticsWriter,
        qualified_dataset,
    )

    settings = Settings()
    if not settings.gcp_project_id:
        pytest.skip("GCP_PROJECT_ID not set")
    client = bigquery.Client(project=settings.gcp_project_id)
    dataset = qualified_dataset(settings.gcp_project_id, settings.bigquery_dataset)
    user_id = f"it-{uuid.uuid4().hex[:12]}"
    yield {
        "client": client,
        "dataset": dataset,
        "user_id": user_id,
        "writer": BigQueryAnalyticsWriter(settings, client=client),
        "queries": AnalyticsQueries(settings, client=client),
    }
    for table in ("documents", "extracted_transactions", "line_items", "extraction_metrics"):
        client.query(
            f"DELETE FROM `{dataset}.{table}` WHERE user_id = @u",  # noqa: S608
            job_config=bigquery.QueryJobConfig(
                query_parameters=[bigquery.ScalarQueryParameter("u", "STRING", user_id)]
            ),
        ).result()


def count(bq: dict[str, Any], table: str, document_id: str) -> int:
    from google.cloud import bigquery

    rows = (
        bq["client"]
        .query(
            f"SELECT COUNT(*) AS n FROM `{bq['dataset']}.{table}` WHERE document_id = @d",  # noqa: S608
            job_config=bigquery.QueryJobConfig(
                query_parameters=[bigquery.ScalarQueryParameter("d", "STRING", document_id)]
            ),
        )
        .result()
    )
    return int(next(iter(rows))["n"])


def rows_for(bq: dict[str, Any], status: str, document_id: str) -> Any:
    from receipt_shared.analytics import build_rows
    from receipt_shared.models.enums import DocumentStatus, DuplicateStatus, ProcessingOutcome
    from receipt_shared.models.extraction import (
        ExtractedDocument,
        ExtractionMetadata,
        ExtractionResult,
        LineItem,
    )
    from receipt_shared.models.validation import ValidationResult
    from receipt_shared.repository import DocumentRecord

    record = DocumentRecord(
        document_id=document_id, user_id=bq["user_id"], status=DocumentStatus.VALIDATING,
        original_filename="r.pdf", bucket="b", object_name=f"uploads/x/{document_id}/r.pdf",
        content_type="application/pdf", size_bytes=1234, page_count=1, object_generation=1,
        processing_attempts=1, processing_duration_ms=5000.0,
        created_at=datetime.now(UTC), extracted_at=datetime.now(UTC),
    )  # fmt: skip
    extraction = ExtractionResult(
        document=ExtractedDocument(
            document_type="receipt", merchant_name="Maple Leaf Cafe",
            document_date=date(2026, 3, 14), currency="CAD", subtotal=Decimal("23.20"),
            tax_amount=Decimal("3.48"), total_amount=Decimal("26.68"), expense_category="meals",
            line_items=[
                LineItem(description="Latte", quantity=Decimal(2),
                         unit_price=Decimal("5.25"), total_price=Decimal("10.50")),
                LineItem(description="Sandwich", quantity=Decimal(1),
                         unit_price=Decimal("12.70"), total_price=Decimal("12.70")),
            ],
        ),
        metadata=ExtractionMetadata(
            model="gemini-3.8-flash", model_version="gemini-3.8-flash", prompt_version="p",
            location="global", latency_ms=4500.0, attempts=1, total_tokens=3000,
        ),
    )  # fmt: skip
    outcome = (
        ProcessingOutcome(status)
        if status in ProcessingOutcome.__members__
        else ProcessingOutcome.VALID
    )
    validation = ValidationResult(
        is_valid=status == "VALID", validation_status=outcome,
        duplicate_status=DuplicateStatus.NOT_DUPLICATE, rules_version="r",
    )  # fmt: skip
    return build_rows(
        record, status=DocumentStatus(status), extraction=extraction, validation=validation,
        now=datetime.now(UTC),
    )  # fmt: skip


def test_writes_are_idempotent(bq: dict[str, Any]) -> None:
    doc_id = uuid.uuid4().hex
    rows = rows_for(bq, "VALID", doc_id)
    bq["writer"].write(rows)
    bq["writer"].write(rows)  # replayed event
    assert count(bq, "documents", doc_id) == 1
    assert count(bq, "extracted_transactions", doc_id) == 1
    assert count(bq, "line_items", doc_id) == 2
    assert count(bq, "extraction_metrics", doc_id) == 1


def test_non_approved_status_removes_transaction(bq: dict[str, Any]) -> None:
    doc_id = uuid.uuid4().hex
    bq["writer"].write(rows_for(bq, "VALID", doc_id))
    bq["writer"].write(rows_for(bq, "REVIEW_REQUIRED", doc_id))
    assert count(bq, "documents", doc_id) == 1
    assert count(bq, "extracted_transactions", doc_id) == 0
    assert count(bq, "line_items", doc_id) == 0


def test_money_is_exact_numeric(bq: dict[str, Any]) -> None:
    rows = bq["queries"].run(
        "total_spending",
        user_id=bq["user_id"],
        start_date=date(2026, 1, 1),
        end_date=date(2026, 12, 31),
    )
    # Only the first test's VALID document remains approved.
    assert rows == [
        {"currency": "CAD", "total_amount": "26.68", "total_tax": "3.48", "transaction_count": 1}
    ]


@pytest.mark.parametrize(
    "name",
    [
        "monthly_spending", "spending_by_merchant", "spending_by_category",
        "average_transaction_value", "document_type_counts", "processing_success_rate",
        "manual_review_rate", "extraction_accuracy_reviews", "extraction_accuracy_evaluation",
    ],
)  # fmt: skip
def test_every_analytics_query_runs(bq: dict[str, Any], name: str) -> None:
    rows = bq["queries"].run(
        name, user_id=bq["user_id"], start_date=date(2020, 1, 1), end_date=date(2030, 12, 31)
    )
    assert isinstance(rows, list)
    if name == "monthly_spending":
        assert rows == [
            {
                "month": "2026-03-01",
                "currency": "CAD",
                "total_amount": "26.68",
                "transaction_count": 1,
            }
        ]
    if name == "processing_success_rate":
        assert rows[0]["processed_documents"] == 2
        assert rows[0]["success_rate"] == 1.0
    if name == "manual_review_rate":
        assert rows[0]["review_required"] == 1
        assert rows[0]["review_rate"] == 0.5
