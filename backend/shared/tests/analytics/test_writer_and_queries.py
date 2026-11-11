import json
from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from google.api_core import exceptions as gexc

from receipt_shared.analytics import (
    QUERY_NAMES,
    AnalyticsQueries,
    AnalyticsRows,
    AnalyticsWriteError,
    BigQueryAnalyticsWriter,
    build_delete_script,
    build_parameters,
    build_write_script,
    load_query,
)
from receipt_shared.analytics.queries import query_parameters
from receipt_shared.config import Settings

SETTINGS = Settings(_env_file=None, gcp_project_id="proj-1", bigquery_dataset="receipt_analytics")


class FakeJob:
    def __init__(
        self, rows: list[dict[str, Any]] | None = None, error: Exception | None = None
    ) -> None:
        self.rows, self.error = rows or [], error

    def result(self, timeout: float | None = None) -> list[dict[str, Any]]:
        if self.error:
            raise self.error
        return self.rows


class FakeClient:
    def __init__(self, job: FakeJob | None = None) -> None:
        self.job = job or FakeJob()
        self.calls: list[dict[str, Any]] = []

    def query(self, sql: str, job_config: Any = None, location: str | None = None) -> FakeJob:
        self.calls.append({"sql": sql, "config": job_config, "location": location})
        return self.job


ROWS = AnalyticsRows(
    document_id="d1",
    document={"document_id": "d1"},
    metrics={"metric_id": "d1:1"},
    transaction={"document_id": "d1", "total_amount": "26.68"},
    line_items=[{"document_id": "d1", "line_number": 1}],
)


# --- writer ------------------------------------------------------------------------------------
def test_script_is_one_transaction_with_merge_and_line_item_replacement() -> None:
    sql = build_write_script("proj-1.receipt_analytics")
    assert sql.startswith("BEGIN")
    assert sql.count("BEGIN TRANSACTION") == 1
    assert "COMMIT TRANSACTION" in sql
    assert "ROLLBACK TRANSACTION" in sql
    assert "MERGE `proj-1.receipt_analytics.documents`" in sql
    assert "MERGE `proj-1.receipt_analytics.extracted_transactions`" in sql
    assert (
        "DELETE FROM `proj-1.receipt_analytics.line_items` WHERE document_id = @document_id" in sql
    )
    assert "INSERT INTO `proj-1.receipt_analytics.line_items`" in sql
    assert "insertAll" not in sql  # no streaming


def test_parameters_are_json_strings() -> None:
    params = dict(build_parameters(ROWS))
    assert params["document_id"] == "d1"
    assert json.loads(params["transaction"] or "") == {"document_id": "d1", "total_amount": "26.68"}
    assert json.loads(params["line_items"] or "") == [{"document_id": "d1", "line_number": 1}]


def test_missing_transaction_and_metrics_become_null_params() -> None:
    params = dict(build_parameters(AnalyticsRows(document_id="d1", document={"document_id": "d1"})))
    assert params["transaction"] is None
    assert params["metrics"] is None
    assert params["line_items"] == "[]"


def test_writer_runs_parameterised_script_in_dataset_location() -> None:
    client = FakeClient()
    BigQueryAnalyticsWriter(SETTINGS, client=client).write(ROWS)
    [call] = client.calls
    assert call["location"] == "US"
    names = {p.name: (p.type_, p.value) for p in call["config"].query_parameters}
    assert names["document_id"] == ("STRING", "d1")
    assert call["config"].labels["operation"] == "document-write"


@pytest.mark.parametrize(
    ("error", "retryable"),
    [
        (gexc.BadRequest("Transaction is aborted due to concurrent update"), True),
        (gexc.BadRequest("Unrecognized name: totl_amount"), False),
        (gexc.Forbidden("Access Denied"), False),
        (gexc.ServiceUnavailable("backend"), True),
        (gexc.InternalServerError("oops"), True),
        (TimeoutError(), True),
    ],
)
def test_write_errors_are_classified(error: Exception, retryable: bool) -> None:
    client = FakeClient(FakeJob(error=error))
    with pytest.raises(AnalyticsWriteError) as info:
        BigQueryAnalyticsWriter(SETTINGS, client=client).write(ROWS)
    assert info.value.retryable is retryable


def test_delete_script_clears_every_table_in_one_transaction() -> None:
    sql = build_delete_script("proj-1.receipt_analytics")
    assert sql.count("BEGIN TRANSACTION") == 1
    assert "ROLLBACK TRANSACTION" in sql
    for table in ("documents", "extracted_transactions", "line_items", "review_records",
                  "extraction_metrics"):  # fmt: skip
        assert (
            f"DELETE FROM `proj-1.receipt_analytics.{table}` WHERE document_id = @document_id"  # noqa: S608
            in sql
        )


def test_writer_delete_is_parameterised() -> None:
    client = FakeClient()
    BigQueryAnalyticsWriter(SETTINGS, client=client).delete("d1")
    [call] = client.calls
    assert "DELETE FROM" in call["sql"]
    assert [(p.name, p.value) for p in call["config"].query_parameters] == [("document_id", "d1")]
    assert call["config"].labels["operation"] == "document-delete"


def test_delete_errors_are_classified() -> None:
    client = FakeClient(FakeJob(error=gexc.ServiceUnavailable("backend")))
    with pytest.raises(AnalyticsWriteError) as info:
        BigQueryAnalyticsWriter(SETTINGS, client=client).delete("d1")
    assert info.value.retryable is True


def test_writer_requires_project() -> None:
    with pytest.raises(ValueError, match="GCP_PROJECT_ID"):
        BigQueryAnalyticsWriter(Settings(_env_file=None, gcp_project_id=None), client=FakeClient())


# --- queries -----------------------------------------------------------------------------------
@pytest.mark.parametrize("name", QUERY_NAMES)
def test_every_query_loads_with_known_parameters(name: str) -> None:
    sql = load_query(name, "proj-1.receipt_analytics")
    assert "{{dataset}}" not in sql
    assert "`proj-1.receipt_analytics." in sql
    params = query_parameters(sql)
    assert params <= {"user_id", "start_date", "end_date", "limit"}
    if name != "extraction_accuracy_evaluation":
        assert "user_id" in params  # per-user data is always filtered by user


def test_unknown_query_rejected() -> None:
    with pytest.raises(KeyError):
        load_query("drop_everything", "p.d")


def test_runner_binds_typed_parameters_and_converts_values() -> None:
    client = FakeClient(
        FakeJob(
            rows=[{"currency": "CAD", "total_amount": Decimal("26.68"), "month": date(2026, 3, 1)}]
        )
    )
    rows = AnalyticsQueries(SETTINGS, client=client).run(
        "monthly_spending", user_id="u1", start_date=date(2026, 1, 1), end_date=date(2026, 12, 31)
    )
    assert rows == [{"currency": "CAD", "total_amount": "26.68", "month": "2026-03-01"}]
    params = {p.name: (p.type_, p.value) for p in client.calls[0]["config"].query_parameters}
    assert params == {
        "user_id": ("STRING", "u1"),
        "start_date": ("DATE", date(2026, 1, 1)),
        "end_date": ("DATE", date(2026, 12, 31)),
    }


def test_runner_refuses_user_query_without_user() -> None:
    with pytest.raises(ValueError, match="user_id"):
        AnalyticsQueries(SETTINGS, client=FakeClient()).run(
            "total_spending", start_date=date(2026, 1, 1), end_date=date(2026, 12, 31)
        )
