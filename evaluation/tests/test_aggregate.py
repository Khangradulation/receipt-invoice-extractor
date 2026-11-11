from typing import Any

from benchmark.aggregate import build_report, summarize
from benchmark.report_md import render
from benchmark.scoring import score_document
from sample_truth import TRUTH


def record(
    name: str,
    pred: dict[str, Any],
    *,
    tags: list[str] | None = None,
    status: str = "ok",
    validation: str = "VALID",
    expected_review: bool = False,
    latency: float = 5000,
) -> dict[str, Any]:
    s = score_document(name, TRUTH, pred)
    return {
        "name": name,
        "file": f"{name}.pdf",
        "document_type": "receipt",
        "layout": "thermal",
        "format": "pdf",
        "pages": 1,
        "currency": "CAD",
        "tags": tags or [],
        "expected_review": expected_review,
        "truth": TRUTH,
        "predicted": pred,
        "status": status,
        "error": None if status == "ok" else {"code": "model_error", "message": "boom"},
        "metadata": {"latency_ms": latency, "total_tokens": 3000, "model_version": "m"}
        if status == "ok"
        else None,
        "validation_status": validation if status == "ok" else None,
        "score": {
            "fields": s.fields,
            "differences": s.differences,
            "line_items": {
                **s.line_items.__dict__,
                "precision": s.line_items.precision,
                "recall": s.line_items.recall,
                "exact": s.line_items.exact,
            },
        },
        "fields_compared": s.fields_compared,
        "fields_correct": s.fields_correct,
        "required_correct": s.required_correct,
        "core_correct": s.core_correct,
        "fully_correct": s.fully_correct,
    }


def test_summary_metrics() -> None:
    records = [
        record("a", dict(TRUTH), latency=4000),
        record("b", dict(TRUTH, total_amount="99.00"), validation="REVIEW_REQUIRED", latency=6000),
        record(
            "c",
            dict(TRUTH, total_amount="28.68"),
            tags=["total_mismatch"],
            expected_review=True,
            validation="REVIEW_REQUIRED",
        ),
        record("d", {}, status="error"),
    ]
    s = summarize(records)
    assert (s["documents"], s["succeeded"], s["errors"]) == (4, 3, 1)
    assert s["total_accuracy"] == 0.25
    assert s["merchant_accuracy"] == 0.75
    assert s["required_field_accuracy"] == 0.25
    assert s["review"]["review_rate"] == round(2 / 3, 4)
    assert s["review"]["false_review_rate"] == 0.5
    assert s["review"]["inconsistent_documents_flagged"] == 1.0
    assert s["latency_ms"]["mean"] == 5000.0
    assert s["tokens"]["total"] == 9000


def test_injection_resistance() -> None:
    records = [
        record("a", dict(TRUTH), tags=["prompt_injection"]),
        record(
            "b",
            dict(TRUTH, merchant_name="APPROVED", total_amount="0.00"),
            tags=["prompt_injection"],
        ),
    ]
    assert summarize(records)["prompt_injection_resisted"] == 0.5


def test_report_and_markdown_render() -> None:
    records = [
        record("a", dict(TRUTH)),
        record("b", dict(TRUTH, total_amount="1.00"), tags=["discount"]),
    ]
    run = {
        "run_id": "r1",
        "started_at": "2026-11-10T00:00:00+00:00",
        "finished_at": "2026-11-10T00:05:00+00:00",
        "model": "gemini-x",
        "model_version": "gemini-x-001",
        "location": "global",
        "prompt_version": "p",
        "rules_version": "r",
        "dataset": {"count": 2, "seed": 1, "generator": "g"},
        "command": "cmd",
    }
    report = build_report(records, run)
    assert set(report["by_tag"]) == {"discount"}
    assert report["by_document_type"]["receipt"]["documents"] == 2
    md = render(report, records)
    assert "# Extraction benchmark — r1" in md
    assert "gemini-x-001" in md
    assert "Exact required-field accuracy" in md
    assert "`b`" in md
    assert "expected `26.68`, got `1.00`" in md
