"""Run the packaged analytics queries (``analytics/sql/*.sql``) with typed parameters."""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal
from importlib import resources
from typing import Any

from receipt_shared.analytics.schema import qualified_dataset
from receipt_shared.config import Settings

QUERY_NAMES: tuple[str, ...] = (
    "total_spending",
    "monthly_spending",
    "spending_by_merchant",
    "spending_by_category",
    "average_transaction_value",
    "document_type_counts",
    "processing_success_rate",
    "manual_review_rate",
    "extraction_accuracy_reviews",
    "extraction_accuracy_evaluation",
)
_PARAM_RE = re.compile(r"@(\w+)")


def load_query(name: str, dataset: str) -> str:
    if name not in QUERY_NAMES:
        raise KeyError(f"unknown analytics query: {name}")
    text = resources.files("receipt_shared.analytics.sql").joinpath(f"{name}.sql").read_text()
    return text.replace("{{dataset}}", dataset)


def query_parameters(sql: str) -> set[str]:
    without_comments = "\n".join(line.split("--", 1)[0] for line in sql.splitlines())
    return set(_PARAM_RE.findall(without_comments))


def _jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, date):
        return value.isoformat()
    return value


class AnalyticsQueries:
    def __init__(self, settings: Settings, *, client: Any | None = None) -> None:
        if not settings.gcp_project_id:
            raise ValueError("GCP_PROJECT_ID is required for BigQuery")
        self._dataset = qualified_dataset(settings.gcp_project_id, settings.bigquery_dataset)
        self._location = settings.bigquery_location
        if client is None:
            from google.cloud import bigquery

            client = bigquery.Client(project=settings.gcp_project_id)
        self._client = client

    def run(
        self,
        name: str,
        *,
        start_date: date,
        end_date: date,
        user_id: str | None = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        from google.cloud import bigquery

        sql = load_query(name, self._dataset)
        wanted = query_parameters(sql)
        available: dict[str, bigquery.ScalarQueryParameter] = {
            "start_date": bigquery.ScalarQueryParameter("start_date", "DATE", start_date),
            "end_date": bigquery.ScalarQueryParameter("end_date", "DATE", end_date),
            "limit": bigquery.ScalarQueryParameter("limit", "INT64", limit),
        }
        if user_id is not None:
            available["user_id"] = bigquery.ScalarQueryParameter("user_id", "STRING", user_id)
        missing = wanted - available.keys()
        if missing:
            raise ValueError(f"query {name} needs parameters: {sorted(missing)}")
        config = bigquery.QueryJobConfig(
            query_parameters=[available[p] for p in sorted(wanted)],
            labels={"app": "receipt-extractor", "operation": "analytics"},
        )
        job = self._client.query(sql, job_config=config, location=self._location)
        return [{k: _jsonable(v) for k, v in row.items()} for row in job.result(timeout=60)]
