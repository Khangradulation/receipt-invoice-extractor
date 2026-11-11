"""BigQuery table definitions: the single source of truth for the analytics schema.

``sql/schema/*.sql`` is generated from these specs (``make sql-schema``) and a unit test fails if
the files drift. The writer also generates its MERGE statements from the same specs, so a column
cannot be added in one place and forgotten in another.

Rows are passed to BigQuery as one JSON string parameter per row and decoded in SQL
(``JSON_VALUE`` + ``CAST``). Money therefore travels as decimal strings and lands in ``NUMERIC``
exactly — never through a float.
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]*$")


@dataclass(frozen=True)
class Column:
    name: str
    type: str  # STRING, INT64, FLOAT64, NUMERIC, BOOL, DATE, TIMESTAMP, ARRAY<STRING>
    required: bool = False
    description: str = ""

    def ddl(self) -> str:
        mode = " NOT NULL" if self.required and not self.type.startswith("ARRAY") else ""
        desc = self.description.replace("'", "\\'")
        options = f" OPTIONS(description='{desc}')" if desc else ""
        return f"{self.name} {self.type}{mode}{options}"

    def from_json(self, param: str) -> str:
        """SQL expression extracting this column from a JSON string parameter."""
        path = f"'$.{self.name}'"
        if self.type == "STRING":
            return f"JSON_VALUE({param}, {path})"
        if self.type == "ARRAY<STRING>":
            return f"IFNULL(JSON_VALUE_ARRAY({param}, {path}), [])"
        if self.type == "BOOL":
            return f"SAFE_CAST(JSON_VALUE({param}, {path}) AS BOOL)"
        return f"CAST(JSON_VALUE({param}, {path}) AS {self.type})"


@dataclass(frozen=True)
class Table:
    name: str
    description: str
    columns: tuple[Column, ...]
    key: tuple[str, ...]
    partition_by: str
    cluster_by: tuple[str, ...] = ()

    @property
    def column_names(self) -> list[str]:
        return [c.name for c in self.columns]

    def ddl(self, dataset: str) -> str:
        cols = ",\n".join(f"  {c.ddl()}" for c in self.columns)
        cluster = f"\nCLUSTER BY {', '.join(self.cluster_by)}" if self.cluster_by else ""
        desc = self.description.replace("'", "\\'")
        return (
            f"CREATE TABLE IF NOT EXISTS `{dataset}.{self.name}` (\n{cols}\n)\n"
            f"PARTITION BY {self.partition_by}{cluster}\n"
            f"OPTIONS(description='{desc}');\n"
        )

    def merge_sql(self, dataset: str, param: str) -> str:
        """MERGE one row (JSON string ``@param``) keyed on ``self.key``: insert or overwrite."""
        select = ",\n    ".join(f"{c.from_json('@' + param)} AS {c.name}" for c in self.columns)
        on = " AND ".join(f"T.{k} = S.{k}" for k in self.key)
        updates = ", ".join(f"{c} = S.{c}" for c in self.column_names if c not in self.key)
        names = ", ".join(self.column_names)
        values = ", ".join(f"S.{c}" for c in self.column_names)
        # Identifiers only (code constants + validated dataset); values come from @param.
        return (
            f"MERGE `{dataset}.{self.name}` T\n"  # noqa: S608
            f"USING (SELECT\n    {select}) S\n"
            f"ON {on}\n"
            f"WHEN MATCHED THEN UPDATE SET {updates}\n"
            f"WHEN NOT MATCHED THEN INSERT ({names}) VALUES ({values});"
        )

    def merge_from_json_array_sql(self, dataset: str, param: str) -> str:
        """Insert elements of the JSON array ``@param`` whose key is not present (idempotent)."""
        select = ",\n    ".join(f"{c.from_json('item')} AS {c.name}" for c in self.columns)
        on = " AND ".join(f"T.{k} = S.{k}" for k in self.key)
        names = ", ".join(self.column_names)
        values = ", ".join(f"S.{c}" for c in self.column_names)
        # Identifiers only (code constants + validated dataset); values come from @param.
        return (
            f"MERGE `{dataset}.{self.name}` T\n"  # noqa: S608
            f"USING (SELECT\n    {select}\n  FROM UNNEST(JSON_QUERY_ARRAY(@{param})) AS item) S\n"
            f"ON {on}\n"
            f"WHEN NOT MATCHED THEN INSERT ({names}) VALUES ({values});"
        )

    def insert_from_json_array_sql(self, dataset: str, param: str) -> str:
        """INSERT every element of the JSON array string ``@param``."""
        select = ",\n    ".join(f"{c.from_json('item')} AS {c.name}" for c in self.columns)
        return (
            f"INSERT INTO `{dataset}.{self.name}` ({', '.join(self.column_names)})\n"
            f"SELECT\n    {select}\n"
            f"FROM UNNEST(JSON_QUERY_ARRAY(@{param})) AS item;"
        )


_MONEY = "NUMERIC"

DOCUMENTS = Table(
    name="documents",
    description="One row per processed document (all outcomes), for operational analytics.",
    key=("document_id",),
    partition_by="DATE(created_at)",
    cluster_by=("user_id", "processing_status"),
    columns=(
        Column("document_id", "STRING", True),
        Column("user_id", "STRING", True),
        Column("document_type", "STRING"),
        Column("processing_status", "STRING", True, "Current status (VALID, REVIEW_REQUIRED, ...)"),
        Column("validation_status", "STRING", description="Latest validation outcome"),
        Column("review_required", "BOOL", description="Initial validation sent it to review"),
        Column("duplicate_status", "STRING"),
        Column("error_count", "INT64"),
        Column("warning_count", "INT64"),
        Column("failed_fields", "ARRAY<STRING>"),
        Column("error_code", "STRING", description="Processing error code if FAILED"),
        Column("content_type", "STRING"),
        Column("size_bytes", "INT64"),
        Column("page_count", "INT64"),
        Column("model_version", "STRING"),
        Column("prompt_version", "STRING"),
        Column("rules_version", "STRING"),
        Column("processing_attempts", "INT64"),
        Column("processing_duration_ms", "FLOAT64"),
        Column("created_at", "TIMESTAMP", True),
        Column("uploaded_at", "TIMESTAMP"),
        Column("completed_at", "TIMESTAMP"),
        Column("loaded_at", "TIMESTAMP", True),
    ),
)

EXTRACTED_TRANSACTIONS = Table(
    name="extracted_transactions",
    description="Approved transactions only (VALID, or APPROVED after review).",
    key=("document_id",),
    partition_by="DATE_TRUNC(document_date, MONTH)",
    cluster_by=("user_id", "expense_category"),
    columns=(
        Column("document_id", "STRING", True),
        Column("user_id", "STRING", True),
        Column("document_type", "STRING", True),
        Column("merchant_name", "STRING", True),
        Column("merchant_address", "STRING"),
        Column("document_date", "DATE", True),
        Column("due_date", "DATE"),
        Column("document_number", "STRING"),
        Column("currency", "STRING", True),
        Column("subtotal", _MONEY),
        Column("tax_amount", _MONEY),
        Column("discount_amount", _MONEY),
        Column("total_amount", _MONEY, True),
        Column("expense_category", "STRING"),
        Column("payment_method", "STRING"),
        Column("processing_status", "STRING", True),
        Column("record_source", "STRING", True, "AI (validated automatically) or REVIEWED"),
        Column("model_version", "STRING"),
        Column("approved_by", "STRING"),
        Column("approved_at", "TIMESTAMP"),
        Column("created_at", "TIMESTAMP", True),
        Column("loaded_at", "TIMESTAMP", True),
    ),
)

LINE_ITEMS = Table(
    name="line_items",
    description="Line items of approved transactions, linked by document_id.",
    key=("document_id", "line_number"),
    partition_by="DATE_TRUNC(document_date, MONTH)",
    cluster_by=("user_id", "document_id"),
    columns=(
        Column("document_id", "STRING", True),
        Column("user_id", "STRING", True),
        Column("line_number", "INT64", True),
        Column("description", "STRING"),
        Column("quantity", _MONEY),
        Column("unit_price", _MONEY),
        Column("total_price", _MONEY),
        Column("currency", "STRING"),
        Column("document_date", "DATE", True),
        Column("loaded_at", "TIMESTAMP", True),
    ),
)

REVIEW_RECORDS = Table(
    name="review_records",
    description="Audit trail of manual review actions and field corrections.",
    key=("review_id",),
    partition_by="DATE(reviewed_at)",
    cluster_by=("user_id", "document_id"),
    columns=(
        Column("review_id", "STRING", True),
        Column("document_id", "STRING", True),
        Column("user_id", "STRING", True),
        Column("action", "STRING", True, "CORRECTION, APPROVE or REJECT"),
        Column("field_name", "STRING"),
        Column("original_value", "STRING", description="Value extracted by Gemini"),
        Column("corrected_value", "STRING"),
        Column("reason", "STRING"),
        Column("reviewer_id", "STRING", True),
        Column("model_version", "STRING"),
        Column("reviewed_at", "TIMESTAMP", True),
    ),
)

EXTRACTION_METRICS = Table(
    name="extraction_metrics",
    description="Per-extraction performance metrics (production and evaluation runs).",
    key=("metric_id",),
    partition_by="DATE(processed_at)",
    cluster_by=("model_version",),
    columns=(
        Column("metric_id", "STRING", True, "document_id:generation, or run_id:document_id"),
        Column("document_id", "STRING", True),
        Column("user_id", "STRING"),
        Column("evaluation_run_id", "STRING", description="Set for benchmark runs (Phase 10)"),
        Column("model", "STRING"),
        Column("model_version", "STRING"),
        Column("prompt_version", "STRING"),
        Column("location", "STRING"),
        Column("mime_type", "STRING"),
        Column("page_count", "INT64"),
        Column("latency_ms", "FLOAT64"),
        Column("gemini_attempts", "INT64"),
        Column("prompt_tokens", "INT64"),
        Column("output_tokens", "INT64"),
        Column("thoughts_tokens", "INT64"),
        Column("total_tokens", "INT64"),
        Column("outcome", "STRING", description="Status after validation"),
        Column("missing_field_count", "INT64"),
        Column("extraction_warning_count", "INT64"),
        Column("fields_compared", "INT64", description="Evaluation only"),
        Column("fields_correct", "INT64", description="Evaluation only"),
        Column("processed_at", "TIMESTAMP", True),
    ),
)

TABLES: tuple[Table, ...] = (
    DOCUMENTS,
    EXTRACTED_TRANSACTIONS,
    LINE_ITEMS,
    REVIEW_RECORDS,
    EXTRACTION_METRICS,
)

DDL_PLACEHOLDER = "{{dataset}}"  # replaced with `project.dataset` by ops/gcp/bootstrap-bigquery.sh


def qualified_dataset(project: str, dataset: str) -> str:
    for part, what in ((project, "project"), (dataset, "dataset")):
        if not _IDENT.match(part):
            raise ValueError(f"invalid BigQuery {what} identifier: {part!r}")
    return f"{project}.{dataset}"


def render_ddl_files() -> dict[str, str]:
    header = (
        "-- Generated from backend/shared/src/receipt_shared/analytics/schema.py — do not edit.\n"
        "-- Regenerate with: make sql-schema\n"
    )
    return {f"{t.name}.sql": header + t.ddl(DDL_PLACEHOLDER) for t in TABLES}


_PARTITION_RE = re.compile(r"^(DATE|DATE_TRUNC)\((\w+)(?:,\s*(DAY|MONTH))?\)$")


def terraform_tables() -> dict[str, Any]:
    """Table definitions for the Terraform bigquery module (schema, partitioning, clustering)."""
    out: dict[str, Any] = {}
    for t in TABLES:
        m = _PARTITION_RE.match(t.partition_by)
        if not m:
            raise ValueError(f"unsupported partition expression: {t.partition_by}")
        func, column, unit = m.groups()
        fields = []
        for c in t.columns:
            repeated = c.type.startswith("ARRAY<")
            fields.append(
                {
                    "name": c.name,
                    "type": c.type[6:-1] if repeated else c.type,
                    "mode": "REPEATED" if repeated else ("REQUIRED" if c.required else "NULLABLE"),
                    "description": c.description,
                }
            )
        out[t.name] = {
            "description": t.description,
            "partition": {
                "field": column,
                "type": "MONTH" if func == "DATE_TRUNC" else (unit or "DAY"),
            },
            "clustering": list(t.cluster_by),
            "schema": fields,
        }
    return out


def render_terraform_tables() -> str:
    return json.dumps(terraform_tables(), indent=2) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Write sql/schema/*.sql from the table specs")
    parser.add_argument("out_dir", type=Path)
    parser.add_argument(
        "--terraform", type=Path, help="Also write the Terraform bigquery module's tables.json"
    )
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    for name, text in render_ddl_files().items():
        (args.out_dir / name).write_text(text)
    print(f"wrote {len(TABLES)} files to {args.out_dir}")
    if args.terraform:
        args.terraform.write_text(render_terraform_tables())
        print(f"wrote {args.terraform}")


if __name__ == "__main__":
    main()
