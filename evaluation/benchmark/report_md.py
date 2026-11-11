"""Render the benchmark report as Markdown."""

from __future__ import annotations

from typing import Any


def pct(v: float | None) -> str:
    return "—" if v is None else f"{v * 100:.1f}%"


def render(report: dict[str, Any], records: list[dict[str, Any]]) -> str:
    run, s = report["run"], report["summary"]
    li, rv, lat = s["line_items"], s["review"], s["latency_ms"]
    out = [
        f"# Extraction benchmark — {run['run_id']}",
        "",
        f"- **Date:** {run['started_at']} (finished {run['finished_at']})",
        f"- **Model:** `{run['model']}` (reported version `{run.get('model_version') or 'n/a'}`), location `{run['location']}`",
        f"- **Prompt version:** `{run['prompt_version']}` · **Validation rules:** `{run['rules_version']}`",
        f"- **Dataset:** {run['dataset']['count']} synthetic documents, seed {run['dataset']['seed']} "
        f"(`{run['dataset']['generator']}`)",
        f"- **Documents:** {s['documents']} · succeeded {s['succeeded']} · errors {s['errors']}",
        f"- **Command:** `{run['command']}`",
        "",
        "## Headline metrics",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| Exact required-field accuracy (merchant, date, total, currency, type all correct) | {pct(s['required_field_accuracy'])} |",
        f"| Core document accuracy (all objectively printed fields correct) | {pct(s['core_document_accuracy'])} |",
        f"| Fully correct documents (core fields + every line item) | {pct(s['fully_correct_documents'])} |",
        f"| Field accuracy (all fields, all documents) | {pct(s['field_accuracy'])} |",
        f"| Merchant accuracy | {pct(s['merchant_accuracy'])} |",
        f"| Date accuracy | {pct(s['date_accuracy'])} |",
        f"| Subtotal accuracy | {pct(s['subtotal_accuracy'])} |",
        f"| Tax accuracy | {pct(s['tax_accuracy'])} |",
        f"| Total accuracy | {pct(s['total_accuracy'])} |",
        f"| Currency accuracy | {pct(s['currency_accuracy'])} |",
        f"| Document type accuracy | {pct(s['document_type_accuracy'])} |",
        f"| Monetary accuracy (subtotal, tax, discount, total) | {pct(s['money_accuracy'])} |",
        f"| Line items precision / recall / F1 | {pct(li['precision'])} / {pct(li['recall'])} / {pct(li['f1'])} |",
        f"| Documents with every line item exact | {pct(li['exact_documents'])} |",
        f"| Hallucination rate (value returned where nothing printed) | {pct(s['hallucination_rate'])} |",
        f"| Review rate (all / clean documents) | {pct(rv['review_rate'])} / {pct(rv['false_review_rate'])} |",
        f"| Inconsistent documents correctly sent to review | {pct(rv['inconsistent_documents_flagged'])} |",
        f"| Prompt-injection documents resisted | {pct(s['prompt_injection_resisted'])} |",
        f"| Latency mean / p50 / p95 | {lat['mean']} / {lat['p50']} / {lat['p95']} ms |",
        f"| Tokens total / mean per document | {s['tokens']['total']:,} / {s['tokens']['mean_per_document']} |",
        "",
        "## Per field",
        "",
        "| Field | Accuracy | Wrong | Missed | Hallucinated |",
        "|---|---|---|---|---|",
    ]
    for f, v in s["fields"].items():
        out.append(
            f"| `{f}` | {pct(v['accuracy'])} | {v['wrong']} | {v['missed']} | {v['hallucinated']} |"
        )
    for title, key in (
        ("Document type", "by_document_type"),
        ("Format", "by_format"),
        ("Layout", "by_layout"),
        ("Currency", "by_currency"),
        ("Scenario tag", "by_tag"),
    ):
        out += [
            "",
            f"## By {title.lower()}",
            "",
            f"| {title} | Docs | Required-field acc. | Core doc acc. | Field acc. | Total acc. | Line-item F1 | Review rate | Mean latency |",
            "|---|---|---|---|---|---|---|---|---|",
        ]
        for g, v in report[key].items():
            out.append(
                f"| {g} | {v['documents']} | {pct(v['required_field_accuracy'])} | {pct(v['core_document_accuracy'])} | "
                f"{pct(v['field_accuracy'])} | {pct(v['total_accuracy'])} | {pct(v['line_item_f1'])} | "
                f"{pct(v['review_rate'])} | {v['mean_latency_ms']} ms |"
            )
    errors = [r for r in records if r["status"] != "ok"]
    out += ["", "## Errors", ""]
    out += [f"- `{r['name']}`: {r['error']['code']} — {r['error']['message']}" for r in errors] or [
        "None."
    ]
    misses = [r for r in records if r["status"] == "ok" and not r["core_correct"]]
    out += ["", f"## Documents with core-field differences ({len(misses)})", ""]
    if not misses:
        out.append("None.")
    for r in misses[:40]:
        diffs = "; ".join(
            f"{f}: expected `{d['truth']}`, got `{d['predicted']}` ({d['outcome']})"
            for f, d in r["score"]["differences"].items()
            if f in report["definitions"]["core_fields"]
        )
        out.append(
            f"- `{r['name']}` [{', '.join(t for t in r['tags'] if ':' not in t) or 'plain'}]: {diffs}"
        )
    out += [
        "",
        "_Synthetic, fictional documents. Results describe this dataset and model configuration only._",
        "",
    ]
    return "\n".join(out)
