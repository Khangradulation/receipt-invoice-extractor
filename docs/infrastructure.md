# Infrastructure (Terraform)

All Google Cloud resources are defined in [`terraform/`](../terraform/README.md). One shared module
(`modules/stack`) describes a full environment; `environments/dev` and `environments/prod` set its
inputs and keep separate remote state.

## What Terraform manages

| Area | Resources |
| --- | --- |
| APIs | Every API the app uses |
| Identity | One service account per workload (API, worker, frontend, Eventarc, kill switch, CI) |
| Storage | Private documents bucket (CORS for the web origins, lifecycle rules, bucket-level IAM) |
| Firestore | `(default)` database with delete protection, composite indexes |
| BigQuery | `receipt_analytics` dataset and its five tables (generated from the Python schema specs) |
| Containers | Artifact Registry repository with cleanup policies |
| Cloud Run | Worker, API and frontend services (created with a placeholder image; CI deploys the real images) |
| Events | Eventarc trigger: object finalized in the bucket → worker |
| CI | Workload Identity Federation for GitHub Actions (this repository, one GitHub environment) and the `receipt-ci-deployer` account; prod also `receipt-ci-terraform` |
| Cost | Monthly budget, Pub/Sub topic and kill-switch permissions |
| Auth | Firebase Authentication (email/password, authorised domains) |
| Monitoring | Log-based metrics and alert policies |

## Safety

- Data stores (bucket, Firestore, dataset, tables) have `prevent_destroy`; Firestore and Cloud Run
  have deletion protection.
- IAM grants are non-authoritative: Terraform adds access, it never removes access it didn't grant.
- Cloud Run image changes are ignored, so CI deploys never conflict with Terraform.
- No service account keys are created. GitHub Actions authenticates with short-lived OIDC tokens.
- `terraform apply` changes the project and is run only after reviewing the plan;
  `terraform destroy` is never run without explicit approval.

## Adopting the existing dev resources

Dev was first built with the `ops/gcp/*.sh` scripts. `environments/dev/imports.tf` adopts those
resources into state, so the first apply changed nothing that was already working. After the
first apply, a fresh `terraform plan` reports **No changes**.

## Keeping BigQuery in sync

`make sql-schema` writes both `sql/schema/*.sql` and `terraform/modules/bigquery/tables.json` from
the same Python specs. A unit test fails if `tables.json` is out of date.

See [deployment.md](deployment.md) for how CI uses this.

## Commands

```bash
make tf-fmt          # formatting check (part of make check)
make tf-validate     # validates dev and prod without cloud access (part of make check)
make tf-plan-dev TF_STATE_BUCKET=<project>-tfstate   # read-only plan against the real project
```
