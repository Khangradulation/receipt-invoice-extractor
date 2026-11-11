# Security

How the system protects documents and accounts, what it assumes, and what it does not cover.

## Controls

| Requirement | How it is met | Where |
| --- | --- | --- |
| Private storage | Documents bucket has public access prevention **enforced** and uniform bucket-level access. Nothing in it is ever public. | `terraform/modules/storage` |
| Authentication | Firebase Authentication (email/password). Every API endpoint except `/health` requires a Firebase ID token, verified on the server (signature, audience, issuer, expiry; 10 s clock skew). | `receipt_api/auth.py` |
| User-level access control | Every document read, review, file URL and delete goes through `owned_record()`. Another user's document returns the same 404 as a missing one, so its existence is never revealed. Listing and analytics queries are filtered by the caller's user ID. Tests cover cross-user access on every route. | `receipt_api/ownership.py`, `api/tests` |
| Least privilege | One service account per workload (API, worker, frontend, Eventarc, build, kill switch, CI deployer, prod CI Terraform). Storage, dataset, registry and service permissions are granted on the resource, not the project. | `terraform/modules/stack` |
| No keys | No service account keys exist. Cloud Run uses its attached identity; URLs are signed through IAM `signBlob`; GitHub Actions uses Workload Identity Federation, limited to this repository, its owner's numeric ID and one GitHub environment. | [deployment.md](deployment.md) |
| Secrets | The app currently needs **no secrets**: Google APIs use the service identity and the Firebase web config is public by design. Cloud Run services can read any future secret from Secret Manager (`secret_env` in `modules/cloud_run_service`), so values never reach code, images or Terraform state. | `terraform/modules/cloud_run_service` |
| HTTPS | Cloud Run serves HTTPS only. The API and frontend send `Strict-Transport-Security`. Signed URLs are `https://storage.googleapis.com`. | |
| Browser hardening | Frontend: Content-Security-Policy (scripts from self only, API, Firebase and Cloud Storage as the only other hosts; no framing), `X-Frame-Options: DENY`, `nosniff`, strict referrer, permissions policy. API: `default-src 'none'` CSP, `no-store`, `nosniff`, `DENY`. | `frontend/security-headers.conf`, `receipt_api/main.py` |
| Upload size and type | The API only issues an upload URL for PDF/PNG/JPEG up to 15 MB with a matching extension. The signed PUT URL is bound to that exact content type and byte count (`x-goog-content-length-range`) and expires in 15 minutes. The worker then re-checks the bytes: size, magic bytes against the declared type, PDF and image integrity, page limit (10), pixel limit (decompression bombs) and the optional client SHA-256. | `routers/documents.py`, `storage/verify.py` |
| Signed URLs | V4, short-lived (15 min), one object, one method. Download URLs force `inline` with a sanitised filename, so a crafted filename can't inject header parameters. | `storage/gcs.py` |
| No credentials in git | `.env` and `terraform.tfvars` are git-ignored. CI scans the **full history** with gitleaks on every PR and deploy. | `.github/workflows/ci.yml` |
| No sensitive data in logs | Logs carry document IDs, statuses, sizes, timings and error types only: never file contents, extracted fields, amounts, merchant names or filenames. Access logs record the path without query strings (signed URLs are never logged). Client request and trace IDs are validated before they are logged. | `receipt_shared/logging.py`, `receipt_shared/http.py` |
| Dependency scanning | `pip-audit` and `npm audit` in CI on every PR and deploy; Dependabot opens weekly update PRs for Python, npm, Docker, Terraform and GitHub Actions. Actions are pinned to commit SHAs. | `.github/` |
| Prompt injection | The prompt tells Gemini the document is untrusted data and to ignore any instructions in it. Output is forced into a JSON schema and then validated by deterministic rules (arithmetic, dates, currencies, duplicates), so a manipulated extraction lands in review instead of being trusted. The benchmark includes injection documents (100% resisted in Phase 10). | `extraction/prompt.py`, `validation/` |
| Abuse | Per-user rate limits per minute: uploads 30, review writes and deletes 60, reads 300. Monthly $10 budget with a kill switch that detaches billing. | `receipt_api/ratelimit.py`, `ops/budget-kill-switch` |

## Retention and deletion

| Data | Kept | Removed |
| --- | --- | --- |
| Original files | Until the user deletes the document | **Delete** removes every stored version immediately. Overwritten versions are otherwise purged after 30 days; abandoned partial uploads after 1 day. |
| Firestore record (extraction, validation, review history) | Until the user deletes the document | Deleted with the document. |
| BigQuery rows (all five tables) | Until the user deletes the document | Deleted with the document, in one transaction. |
| Application logs | Cloud Logging default retention (30 days) | Automatic. Logs never contain document contents. |
| Build artifacts | Images: cleanup policy keeps recent tags only; Cloud Build staging: 30 days | Automatic. |

Deleting a document (`DELETE /api/v1/documents/{id}`, the **Delete** button on a document) removes
the file, then the analytics rows, then the record. If a step fails, the record remains and the
user can retry. Deletion is refused (409) while an upload link is still valid or the worker holds
a live processing lease, so nothing can be written back afterwards.

## Development data

Development, tests and the benchmark use synthetic documents only (`evaluation/samples`,
`evaluation/synthetic`). Real receipts should not be uploaded to the dev environment.

## Assumptions

- Google Cloud, Firebase Authentication and Gemini on Vertex AI are trusted processors. Document
  contents are sent to Gemini (Vertex AI, which does not use customer data for training).
- Firebase ID tokens are short-lived (1 hour) and are the only credential the browser holds; they
  live in Firebase's own browser storage.
- People with Owner/Editor on the GCP project, or admin on the GitHub repository, are trusted.
- Users are individuals; there are no shared workspaces or admin roles in the app.

## Known limitations

- **Token revocation** is not checked on each request (it costs a call per request); a disabled or
  signed-out user's token keeps working until it expires (at most 1 hour).
- **Rate limits** are per API instance (in memory), so the effective limit scales with the number
  of instances (max 3).
- **No malware scanning** of uploads. Files are only ever opened by the worker's parsers (with
  size, page and pixel limits) and shown to their owner from `storage.googleapis.com`, a different
  origin from the app.
- **CSP allows inline styles** (`'unsafe-inline'` in `style-src`), required by the charts library.
- **Email verification and MFA** are not required for sign-in.
- **Encryption** uses Google-managed keys (encrypted at rest by default); customer-managed keys
  (CMEK) are not configured.
- **Legacy Cloud Run URLs** (`...-z5wqv4rxrq-uc.a.run.app`) also reach the services; they are not
  allowed for sign-in or uploads, so only the `...-PROJECT_NUMBER.REGION.run.app` URLs work.
- **Container image vulnerability scanning** (Artifact Analysis) is not enabled because it is billed
  per image; dependencies are audited in CI instead.
- **Production** reviewers on the `production` GitHub environment need a paid GitHub plan for a
  private repository.
