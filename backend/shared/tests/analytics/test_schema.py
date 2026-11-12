from pathlib import Path

import pytest

from receipt_shared.analytics.schema import (
    TABLES,
    qualified_dataset,
    render_ddl_files,
    render_terraform_tables,
    terraform_tables,
)

SQL_DIR = Path(__file__).resolve().parents[4] / "sql" / "schema"


def test_required_tables_exist() -> None:
    assert {t.name for t in TABLES} == {
        "documents",
        "extracted_transactions",
        "line_items",
        "review_records",
        "extraction_metrics",
    }


def test_sql_schema_files_match_specs() -> None:
    """sql/schema/*.sql is generated; regenerate with `make sql-schema` if this fails."""
    expected = render_ddl_files()
    actual = {p.name: p.read_text() for p in SQL_DIR.glob("*.sql")}
    assert actual == expected


def test_money_columns_are_numeric_and_dates_are_date() -> None:
    types = {(t.name, c.name): c.type for t in TABLES for c in t.columns}
    for col in ("subtotal", "tax_amount", "discount_amount", "total_amount"):
        assert types[("extracted_transactions", col)] == "NUMERIC"
    for col in ("quantity", "unit_price", "total_price"):
        assert types[("line_items", col)] == "NUMERIC"
    assert types[("extracted_transactions", "document_date")] == "DATE"
    assert types[("documents", "created_at")] == "TIMESTAMP"


def test_spec_required_columns_present() -> None:
    tx = {c.name for c in TABLES[1].columns}
    assert {
        "document_id", "user_id", "document_type", "merchant_name", "document_date",
        "document_number", "currency", "subtotal", "tax_amount", "discount_amount",
        "total_amount", "expense_category", "processing_status", "model_version", "created_at",
    } <= tx  # fmt: skip


@pytest.mark.parametrize("table", TABLES, ids=lambda t: t.name)
def test_keys_are_columns_and_merge_covers_all_columns(table: object) -> None:
    from receipt_shared.analytics.schema import Table

    assert isinstance(table, Table)
    assert set(table.key) <= set(table.column_names)
    sql = table.merge_sql("p.d", "row")
    for name in table.column_names:
        assert f"AS {name}" in sql
    assert f"MERGE `p.d.{table.name}`" in sql


def test_numeric_values_are_cast_from_json_strings() -> None:
    sql = TABLES[1].merge_sql("p.d", "row")
    assert "CAST(JSON_VALUE(@row, '$.total_amount') AS NUMERIC)" in sql


@pytest.mark.parametrize("bad", ["p;DROP", "p.d", "a b", ""])
def test_qualified_dataset_rejects_bad_identifiers(bad: str) -> None:
    with pytest.raises(ValueError, match="invalid BigQuery"):
        qualified_dataset(bad, "receipt_analytics")


def test_qualified_dataset_ok() -> None:
    assert qualified_dataset("my-project-123", "receipt_analytics") == (
        "my-project-123.receipt_analytics"
    )


def test_terraform_tables_match_specs() -> None:
    """terraform/modules/bigquery/tables.json is generated; regenerate with `make sql-schema`."""
    path = SQL_DIR.parents[1] / "terraform" / "modules" / "bigquery" / "tables.json"
    assert path.read_text() == render_terraform_tables()


def test_terraform_partitioning_and_modes() -> None:
    tables = terraform_tables()
    assert tables["documents"]["partition"] == {"field": "created_at", "type": "DAY"}
    assert tables["extracted_transactions"]["partition"] == {
        "field": "document_date",
        "type": "MONTH",
    }
    failed = next(f for f in tables["documents"]["schema"] if f["name"] == "failed_fields")
    assert (failed["type"], failed["mode"]) == ("STRING", "REPEATED")
    total = next(
        f for f in tables["extracted_transactions"]["schema"] if f["name"] == "total_amount"
    )
    assert (total["type"], total["mode"]) == ("NUMERIC", "REQUIRED")
