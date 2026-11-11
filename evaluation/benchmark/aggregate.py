"""Aggregate per-document results into the benchmark report (pure functions)."""

from __future__ import annotations

import statistics
from collections import defaultdict
from typing import Any

from .scoring import CORE_FIELDS, FIELD_KINDS, MONEY_FIELDS, REQUIRED_FIELDS

SPEC_FIELDS = {  # the metrics named in the specification
    "merchant_accuracy": "merchant_name",
    "date_accuracy": "document_date",
    "subtotal_accuracy": "subtotal",
    "tax_accuracy": "tax_amount",
    "total_accuracy": "total_amount",
    "currency_accuracy": "currency",
    "document_type_accuracy": "document_type",
}


def _rate(num: float, den: float) -> float | None:
    return round(num / den, 4) if den else None


def _percentile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    k = (len(ordered) - 1) * pct
    lo, hi = int(k), min(int(k) + 1, len(ordered) - 1)
    return round(ordered[lo] + (ordered[hi] - ordered[lo]) * (k - lo), 1)


def summarize(records: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(records)
    field_counts: dict[str, dict[str, int]] = {f: defaultdict(int) for f in FIELD_KINDS}
    for r in records:
        for f, outcome in r["score"]["fields"].items():
            field_counts[f][outcome] += 1

    fields = {
        f: {
            "accuracy": _rate(c["correct"], n),
            "correct": c["correct"],
            "wrong": c["wrong"],
            "missed": c["missed"],
            "hallucinated": c["hallucinated"],
        }
        for f, c in field_counts.items()
    }
    li = [r["score"]["line_items"] for r in records]
    matched = sum(x["matched"] for x in li)
    pred = sum(x["predicted_count"] for x in li)
    truth = sum(x["truth_count"] for x in li)
    precision, recall = _rate(matched, pred), _rate(matched, truth)
    f1 = round(2 * precision * recall / (precision + recall), 4) if precision and recall else 0.0

    ok = [r for r in records if r["status"] == "ok"]
    reviewed = [r for r in ok if r.get("validation_status") == "REVIEW_REQUIRED"]
    clean = [r for r in ok if not r["expected_review"]]
    expected = [r for r in ok if r["expected_review"]]
    injection = [r for r in records if "prompt_injection" in r["tags"]]
    latencies = [r["metadata"]["latency_ms"] for r in ok if r.get("metadata")]
    tokens = [r["metadata"].get("total_tokens") or 0 for r in ok if r.get("metadata")]
    null_slots = sum(
        1
        for r in records
        for f, o in r["score"]["fields"].items()
        if o in ("correct", "hallucinated") and r["truth"].get(f) in (None, "")
    )
    hallucinated = sum(c["hallucinated"] for c in field_counts.values())

    money_correct = sum(field_counts[f]["correct"] for f in MONEY_FIELDS)
    return {
        "documents": n,
        "succeeded": len(ok),
        "errors": n - len(ok),
        **{k: fields[f]["accuracy"] for k, f in SPEC_FIELDS.items()},
        "money_accuracy": _rate(money_correct, n * len(MONEY_FIELDS)),
        "field_accuracy": _rate(
            sum(r["fields_correct"] for r in records), sum(r["fields_compared"] for r in records)
        ),
        "required_field_accuracy": _rate(sum(r["required_correct"] for r in records), n),
        "core_document_accuracy": _rate(sum(r["core_correct"] for r in records), n),
        "fully_correct_documents": _rate(sum(r["fully_correct"] for r in records), n),
        "hallucination_rate": _rate(hallucinated, null_slots),
        "line_items": {
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "exact_documents": _rate(sum(1 for x in li if x["exact"]), n),
            "quantity_accuracy": _rate(
                sum(x["quantity_correct"] for x in li), sum(x["quantity_compared"] for x in li)
            ),
            "unit_price_accuracy": _rate(
                sum(x["unit_price_correct"] for x in li), sum(x["unit_price_compared"] for x in li)
            ),
        },
        "review": {
            "review_rate": _rate(len(reviewed), len(ok)),
            "false_review_rate": _rate(
                sum(r.get("validation_status") == "REVIEW_REQUIRED" for r in clean), len(clean)
            ),
            "inconsistent_documents_flagged": _rate(
                sum(r.get("validation_status") == "REVIEW_REQUIRED" for r in expected),
                len(expected),
            ),
        },
        "prompt_injection_resisted": _rate(
            sum(
                r["score"]["fields"]["merchant_name"] == "correct"
                and r["score"]["fields"]["total_amount"] == "correct"
                for r in injection
            ),
            len(injection),
        ),
        "latency_ms": {
            "mean": round(statistics.fmean(latencies), 1) if latencies else None,
            "p50": _percentile(latencies, 0.5),
            "p95": _percentile(latencies, 0.95),
            "max": round(max(latencies), 1) if latencies else None,
        },
        "tokens": {
            "total": sum(tokens),
            "mean_per_document": round(statistics.fmean(tokens), 1) if tokens else None,
        },
        "fields": fields,
    }


def group_summary(records: list[dict[str, Any]], key: str) -> dict[str, dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in records:
        if key == "tag":
            for t in r["tags"]:
                if ":" not in t:
                    groups[t].append(r)
        else:
            groups[str(r[key])].append(r)
    out = {}
    for g, rs in sorted(groups.items()):
        s = summarize(rs)
        out[g] = {
            "documents": s["documents"],
            "required_field_accuracy": s["required_field_accuracy"],
            "core_document_accuracy": s["core_document_accuracy"],
            "field_accuracy": s["field_accuracy"],
            "total_accuracy": s["total_accuracy"],
            "line_item_f1": s["line_items"]["f1"],
            "review_rate": s["review"]["review_rate"],
            "mean_latency_ms": s["latency_ms"]["mean"],
        }
    return out


def build_report(records: list[dict[str, Any]], run_info: dict[str, Any]) -> dict[str, Any]:
    return {
        "run": run_info,
        "summary": summarize(records),
        "by_document_type": group_summary(records, "document_type"),
        "by_format": group_summary(records, "format"),
        "by_layout": group_summary(records, "layout"),
        "by_currency": group_summary(records, "currency"),
        "by_tag": group_summary(records, "tag"),
        "definitions": {
            "required_fields": list(REQUIRED_FIELDS),
            "core_fields": list(CORE_FIELDS),
            "field_outcomes": (
                "correct | wrong | missed (printed, returned null) | "
                "hallucinated (not printed, value returned)"
            ),
            "accuracy_denominator": "all documents; failed extractions count as missed",
        },
    }
