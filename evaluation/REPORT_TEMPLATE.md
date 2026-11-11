# Extraction benchmark — <run id>

> Generated automatically by `evaluation/run_benchmark.py` (`report.md` in each run folder).
> This template documents the sections; never fill it in by hand.

- **Date:** start / finish (UTC)
- **Model:** configured model, the version reported by Vertex AI, and the location
- **Prompt version / validation rules version**
- **Dataset:** count, seed, generator
- **Documents:** total · succeeded · errors
- **Command:** exact command to reproduce

## Headline metrics
Exact required-field accuracy · core document accuracy · fully correct documents · field accuracy ·
merchant / date / subtotal / tax / total / currency / document-type accuracy · monetary accuracy ·
line-item precision / recall / F1 · documents with every line item exact · hallucination rate ·
review rate (all / clean) · inconsistent documents flagged · prompt-injection resistance ·
latency mean / p50 / p95 · tokens.

## Per field
Accuracy plus counts of wrong / missed / hallucinated for each of the 13 fields.

## Breakdowns
By document type, format, layout, currency and scenario tag.

## Errors
Documents whose extraction failed (counted as missed in the accuracy figures).

## Documents with core-field differences
Expected vs. predicted for every core-field mismatch (synthetic data, so safe to show).
