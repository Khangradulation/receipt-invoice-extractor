"""Run the extraction benchmark against the labelled synthetic dataset.

    make evaluate                                   # full dataset (billable Gemini calls)
    cd backend && uv run python ../evaluation/run_benchmark.py --limit 5
    cd backend && uv run python ../evaluation/run_benchmark.py --run-id <id>   # resume a run
    cd backend && uv run python ../evaluation/run_benchmark.py --to-bigquery   # also log metrics

Writes evaluation/reports/<run_id>/{results.jsonl, report.json, report.md}.
"""

from __future__ import annotations

import argparse
import json
import shlex
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from benchmark.aggregate import build_report  # noqa: E402
from benchmark.report_md import render  # noqa: E402
from benchmark.scoring import score_document  # noqa: E402
from receipt_shared.config import get_settings  # noqa: E402
from receipt_shared.extraction import ExtractionError, GeminiExtractor, inspect_document  # noqa: E402
from receipt_shared.extraction.prompt import PROMPT_VERSION  # noqa: E402
from receipt_shared.validation import RULES_VERSION, DocumentValidator  # noqa: E402

VALIDATION_DAY = date(2026, 11, 10)  # dataset dates are in 2026; fixed so results are reproducible


def load_manifest(dataset: Path) -> list[dict[str, Any]]:
    path = dataset / "manifest.jsonl"
    if not path.exists():
        raise SystemExit(f"{path} not found — run `make dataset` first")
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def select_documents(
    manifest: list[dict[str, Any]], document_type: str | None, limit: int | None
) -> list[dict[str, Any]]:
    chosen = [m for m in manifest if document_type in (None, m["document_type"])]
    return chosen[:limit]


def evaluate_one(
    entry: dict[str, Any], dataset: Path, extractor: GeminiExtractor, settings: Any
) -> dict[str, Any]:
    truth = json.loads((dataset / f"{entry['name']}.truth.json").read_text())
    record: dict[str, Any] = {**entry, "truth": truth, "status": "ok"}
    predicted: dict[str, Any] = {}
    try:
        doc_input = inspect_document(
            (dataset / entry["file"]).read_bytes(), settings, filename=entry["file"]
        )
        result = extractor.extract(doc_input, document_id=f"eval-{entry['name']}")
        predicted = result.document.model_dump(mode="json")
        record["metadata"] = result.metadata.model_dump(mode="json")
        record["warnings"] = result.warnings
        validation = DocumentValidator(settings=settings).validate(
            result.document,
            document_id=entry["name"],
            user_id="eval",
            file_sha256=doc_input.sha256,
            extraction_warnings=result.warnings,
            today=VALIDATION_DAY,
        )
        record["validation_status"] = validation.validation_status.value
        record["validation_errors"] = [e.code.value for e in validation.validation_errors]
    except ExtractionError as exc:
        record["status"] = "error"
        record["error"] = {"code": exc.code, "message": exc.message}
    record["predicted"] = predicted
    score = score_document(entry["name"], truth, predicted)
    record["score"] = {
        "fields": score.fields,
        "differences": score.differences,
        "line_items": {
            **score.line_items.__dict__,
            "precision": score.line_items.precision,
            "recall": score.line_items.recall,
            "exact": score.line_items.exact,
        },
    }
    record.update(
        fields_compared=score.fields_compared,
        fields_correct=score.fields_correct,
        required_correct=score.required_correct,
        core_correct=score.core_correct,
        fully_correct=score.fully_correct,
    )
    return record


def write_bigquery(records: list[dict[str, Any]], run_id: str, settings: Any) -> int:
    """Log one extraction_metrics row per document (idempotent MERGE on metric_id)."""
    from google.cloud import bigquery

    from receipt_shared.analytics.schema import EXTRACTION_METRICS, qualified_dataset

    dataset = qualified_dataset(settings.gcp_project_id, settings.bigquery_dataset)
    rows = []
    for r in records:
        md = r.get("metadata") or {}
        rows.append(
            {
                "metric_id": f"{run_id}:{r['name']}",
                "document_id": r["name"],
                "user_id": None,
                "evaluation_run_id": run_id,
                "model": md.get("model"),
                "model_version": md.get("model_version"),
                "prompt_version": md.get("prompt_version"),
                "location": md.get("location"),
                "mime_type": {"pdf": "application/pdf", "png": "image/png", "jpg": "image/jpeg"}[
                    r["format"]
                ],
                "page_count": r["pages"],
                "latency_ms": md.get("latency_ms"),
                "gemini_attempts": md.get("attempts"),
                "prompt_tokens": md.get("prompt_tokens"),
                "output_tokens": md.get("output_tokens"),
                "thoughts_tokens": md.get("thoughts_tokens"),
                "total_tokens": md.get("total_tokens"),
                "outcome": r.get("validation_status") or "ERROR",
                "missing_field_count": len((r.get("predicted") or {}).get("missing_fields") or []),
                "extraction_warning_count": len(r.get("warnings") or []),
                "fields_compared": r["fields_compared"],
                "fields_correct": r["fields_correct"],
                "processed_at": datetime.now(UTC).isoformat(),
            }
        )
    sql = EXTRACTION_METRICS.merge_from_json_array_sql(dataset, "rows")
    config = bigquery.QueryJobConfig(
        query_parameters=[bigquery.ScalarQueryParameter("rows", "STRING", json.dumps(rows))]
    )
    bigquery.Client(project=settings.gcp_project_id).query(
        sql, job_config=config, location=settings.bigquery_location
    ).result()
    return len(rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--dataset", type=Path, default=HERE / "dataset")
    parser.add_argument("--out", type=Path, default=HERE / "reports")
    parser.add_argument("--run-id", help="Resume or name a run (default: timestamp)")
    parser.add_argument("--limit", type=int, help="Only the first N documents")
    parser.add_argument(
        "--document-type", choices=["receipt", "invoice"], help="Only this document type"
    )
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--model", help="Override GEMINI_MODEL")
    parser.add_argument(
        "--to-bigquery", action="store_true", help="Log per-document metrics to BigQuery"
    )
    args = parser.parse_args(argv)

    settings = get_settings()
    if args.model:
        settings = settings.model_copy(update={"gemini_model": args.model})
    manifest = select_documents(load_manifest(args.dataset), args.document_type, args.limit)
    run_id = (
        args.run_id or datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + f"-{settings.gemini_model}"
    )
    run_dir = args.out / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    results_path = run_dir / "results.jsonl"

    done: dict[str, dict[str, Any]] = {}
    if results_path.exists():  # resume: keep successful results, retry errors
        for line in results_path.read_text().splitlines():
            rec = json.loads(line)
            if rec["status"] == "ok":
                done[rec["name"]] = rec
    todo = [e for e in manifest if e["name"] not in done]
    started = datetime.now(UTC)
    print(
        f"run {run_id}: {len(manifest)} documents ({len(done)} already done), model {settings.gemini_model}"
    )

    extractor = GeminiExtractor(settings)
    lock = threading.Lock()
    with results_path.open("w") as fh:
        for rec in done.values():
            fh.write(json.dumps(rec) + "\n")
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = {
                pool.submit(evaluate_one, e, args.dataset, extractor, settings): e for e in todo
            }
            for i, fut in enumerate(as_completed(futures), start=1):
                rec = fut.result()
                with lock:
                    fh.write(json.dumps(rec) + "\n")
                    fh.flush()
                    done[rec["name"]] = rec
                mark = "ok " if rec["status"] == "ok" else "ERR"
                print(
                    f"  [{i:>3}/{len(todo)}] {mark} {rec['name']}: {rec['fields_correct']}/{rec['fields_compared']} fields"
                )

    records = [done[e["name"]] for e in manifest if e["name"] in done]
    dataset_meta = json.loads((args.dataset / "dataset.json").read_text())
    versions = {r["metadata"]["model_version"] for r in records if r.get("metadata")}
    run_info = {
        "run_id": run_id,
        "started_at": started.isoformat(timespec="seconds"),
        "finished_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "model": settings.gemini_model,
        "model_version": ", ".join(sorted(v for v in versions if v)) or None,
        "location": settings.gemini_location,
        "prompt_version": PROMPT_VERSION,
        "rules_version": RULES_VERSION,
        "dataset": dataset_meta,
        "command": "uv run python ../evaluation/run_benchmark.py "
        + " ".join(shlex.quote(a) for a in (argv or sys.argv[1:])),
    }
    report = build_report(records, run_info)
    (run_dir / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    (run_dir / "report.md").write_text(render(report, records))
    if args.to_bigquery:
        print(
            f"logged {write_bigquery(records, run_id, settings)} rows to BigQuery extraction_metrics"
        )
    s = report["summary"]
    print(
        f"\nrequired-field accuracy {s['required_field_accuracy']}, field accuracy {s['field_accuracy']}, "
        f"errors {s['errors']} -> {run_dir / 'report.md'}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
