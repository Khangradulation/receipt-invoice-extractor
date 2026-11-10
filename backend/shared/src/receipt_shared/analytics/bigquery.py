"""Idempotent BigQuery writes: one atomic transaction per document.

Every write MERGEs the document's rows on their keys, and replaces its line items
(DELETE + INSERT) inside the same multi-statement transaction. Re-running a write for the same
document — a redelivered event, a retry, a re-approval — leaves exactly one row per key. DML is
used instead of streaming inserts, because streamed rows can't be updated or deleted for a while
after insertion.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from receipt_shared.analytics.rows import AnalyticsRows
from receipt_shared.analytics.schema import (
    DOCUMENTS,
    EXTRACTED_TRANSACTIONS,
    EXTRACTION_METRICS,
    LINE_ITEMS,
    REVIEW_RECORDS,
    qualified_dataset,
)
from receipt_shared.config import Settings

logger = logging.getLogger("receipt.analytics")


class AnalyticsWriteError(RuntimeError):
    """BigQuery write failed. ``retryable`` is False only for errors a retry can't fix."""

    def __init__(self, message: str, *, retryable: bool) -> None:
        super().__init__(message)
        self.retryable = retryable


def build_write_script(dataset: str) -> str:
    # Only identifiers are interpolated: column/table names from code constants and a dataset
    # name validated by qualified_dataset(). All data values are query parameters.
    return f"""
BEGIN
  BEGIN TRANSACTION;
  {DOCUMENTS.merge_sql(dataset, "document")}
  IF @metrics IS NOT NULL THEN
    {EXTRACTION_METRICS.merge_sql(dataset, "metrics")}
  END IF;
  IF @transaction IS NOT NULL THEN
    {EXTRACTED_TRANSACTIONS.merge_sql(dataset, "transaction")}
    DELETE FROM `{dataset}.{LINE_ITEMS.name}` WHERE document_id = @document_id;
    {LINE_ITEMS.insert_from_json_array_sql(dataset, "line_items")}
  ELSE
    DELETE FROM `{dataset}.{EXTRACTED_TRANSACTIONS.name}` WHERE document_id = @document_id;
    DELETE FROM `{dataset}.{LINE_ITEMS.name}` WHERE document_id = @document_id;
  END IF;
  IF ARRAY_LENGTH(JSON_QUERY_ARRAY(@review_records)) > 0 THEN
    {REVIEW_RECORDS.merge_from_json_array_sql(dataset, "review_records")}
  END IF;
  COMMIT TRANSACTION;
EXCEPTION WHEN ERROR THEN
  ROLLBACK TRANSACTION;
  RAISE USING MESSAGE = @@error.message;
END;
""".strip()  # noqa: S608


def _dumps(value: Any) -> str | None:
    return None if value is None else json.dumps(value, separators=(",", ":"))


def build_parameters(rows: AnalyticsRows) -> list[tuple[str, str | None]]:
    return [
        ("document_id", rows.document_id),
        ("document", _dumps(rows.document)),
        ("metrics", _dumps(rows.metrics)),
        ("transaction", _dumps(rows.transaction)),
        ("line_items", _dumps(rows.line_items) or "[]"),
        ("review_records", _dumps(rows.review_records) or "[]"),
    ]


class BigQueryAnalyticsWriter:
    def __init__(self, settings: Settings, *, client: Any | None = None) -> None:
        if not settings.gcp_project_id:
            raise ValueError("GCP_PROJECT_ID is required for BigQuery")
        self._dataset = qualified_dataset(settings.gcp_project_id, settings.bigquery_dataset)
        self._location = settings.bigquery_location
        if client is None:
            from google.cloud import bigquery

            client = bigquery.Client(project=settings.gcp_project_id)
        self._client = client
        self._script = build_write_script(self._dataset)

    def write(self, rows: AnalyticsRows) -> None:
        from google.api_core import exceptions as gexc
        from google.cloud import bigquery

        config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter(name, "STRING", value)
                for name, value in build_parameters(rows)
            ],
            labels={"app": "receipt-extractor", "operation": "document-write"},
        )
        start = time.perf_counter()
        try:
            job = self._client.query(self._script, job_config=config, location=self._location)
            job.result(timeout=120)
        except (gexc.BadRequest, gexc.NotFound, gexc.Forbidden) as exc:
            # Concurrent transactions on the same table are reported as 400 "aborted due to
            # concurrent update"; those are worth retrying. Schema/permission errors are not.
            message = str(getattr(exc, "message", exc))
            retryable = "concurrent" in message.lower() or "aborted" in message.lower()
            logger.error(
                "bigquery write failed",
                extra={"document_id": rows.document_id, "retryable": retryable,
                       "error_type": type(exc).__name__},
            )  # fmt: skip
            raise AnalyticsWriteError(
                f"BigQuery write failed: {type(exc).__name__}", retryable=retryable
            ) from exc
        except (gexc.GoogleAPIError, TimeoutError, OSError) as exc:
            logger.error(
                "bigquery write failed",
                extra={"document_id": rows.document_id, "retryable": True,
                       "error_type": type(exc).__name__},
            )  # fmt: skip
            raise AnalyticsWriteError(
                f"BigQuery write failed: {type(exc).__name__}", retryable=True
            ) from exc
        logger.info(
            "bigquery write completed",
            extra={
                "document_id": rows.document_id,
                "has_transaction": rows.transaction is not None,
                "line_item_count": len(rows.line_items),
                "duration_ms": round((time.perf_counter() - start) * 1000, 1),
            },
        )
