# Documentation

Architecture, setup, deployment, security and evaluation docs. Each phase adds to these; Phase 16 completes them.

- [setup.md](setup.md) — local development setup
- [extraction.md](extraction.md) — Gemini extraction engine
- [../ops/budget-kill-switch/README.md](../ops/budget-kill-switch/README.md) — $10 budget hard stop
- [validation.md](validation.md) — validation engine and outcomes
- [storage.md](storage.md) — uploads, bucket layout and security controls
- [processing.md](processing.md) — event-driven worker, idempotency and retries
- [analytics.md](analytics.md) — BigQuery schema, idempotent writes and analytics queries
- [api.md](api.md) — REST API reference, pagination, errors, review semantics
- [frontend.md](frontend.md) — pages, auth flow, configuration, tests
- [review.md](review.md) — human-in-the-loop review workflow, audit trail, concurrency
- [evaluation.md](evaluation.md) — extraction benchmark: dataset, scoring, results
- [infrastructure.md](infrastructure.md) — Terraform: what it manages, safety, state
- [deployment.md](deployment.md) — CI/CD workflows, keyless auth, smoke test, releases
- [security.md](security.md) — security controls, retention and deletion, assumptions, limitations
- [monitoring.md](monitoring.md) — logs, metrics, dashboard, alerts and first steps
