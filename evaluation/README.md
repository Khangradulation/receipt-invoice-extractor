# Evaluation

Reproducible extraction benchmark on labelled synthetic documents. See
[docs/evaluation.md](../docs/evaluation.md).

- `synthetic/`: dataset generator (`make dataset`)
- `benchmark/`: scoring, aggregation, Markdown report
- `run_benchmark.py`: runner (`make evaluate`)
- `reports/<run_id>/`: `report.md` and `report.json` (committed); `results.jsonl` (local)
- `samples/`: a handful of hand-made samples used by the live integration tests
- `tests/`: unit tests (run by `make check`)
