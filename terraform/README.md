# Terraform

All Google Cloud infrastructure for the receipt extractor, as code.

```
terraform/
  modules/
    stack/                 everything one environment needs (composes the modules below)
    project_services/      enabled APIs
    service_accounts/      one service account per workload
    project_iam/           non-authoritative project role grants
    storage/               private documents bucket (+ bucket IAM)
    firestore/             Firestore database + composite indexes
    bigquery/              dataset + tables (tables.json generated from the Python specs)
    artifact_registry/     Docker repository + cleanup policies
    cloud_run_service/     a Cloud Run v2 service (+ invokers)
    eventarc_gcs_trigger/  Cloud Storage finalized events -> Cloud Run
    github_wif/            keyless GitHub Actions auth + CI deployer service account
    budget_guard/          monthly budget -> Pub/Sub, kill-switch account and permissions
    identity/              Firebase Auth (email/password, authorised domains)
    monitoring/            log-based metrics, alert policies, email channel, dashboard
  environments/
    dev/                   dev project; imports.tf adopts resources created by ops/gcp/*.sh
    prod/                  separate project; bootstrap once by hand, then only via deploy-prod
```

## Usage

```bash
PROJECT_ID=<project> ./ops/gcp/bootstrap-tfstate.sh        # once: remote-state bucket
cd terraform/environments/dev
cp terraform.tfvars.example terraform.tfvars                # fill in (git-ignored)
terraform init -backend-config="bucket=<project>-tfstate"
terraform plan                                              # read-only
terraform apply                                             # changes the project: review the plan first
```

Or from the repository root: `make tf-fmt` and `make tf-validate` (both run in `make check`), and
`make tf-plan-dev`.

## Conventions

- **State:** GCS backend, one prefix per environment (`receipt-extractor/dev`,
  `receipt-extractor/prod`). The bucket is versioned, private and locked by the backend's lock
  object.
- **Safety:** the documents bucket, Firestore database, BigQuery dataset and tables have
  `prevent_destroy`. Firestore and Cloud Run services have deletion protection. `terraform destroy`
  is never run without explicit approval.
- **Least privilege:** each workload has its own service account. Bucket, dataset, repository and
  service permissions are granted on that resource only. IAM grants are non-authoritative (they
  never remove other access).
- **Images:** Terraform creates the Cloud Run services (with a public placeholder image) and owns
  their configuration; CI deploys the real images (image changes are ignored by Terraform). See
  [docs/deployment.md](../docs/deployment.md).
- **Web origin:** the frontend's predictable run.app URL is always added to CORS and Firebase's
  authorised domains; `web_origins` / `auth_domains` are extras (e.g. a custom domain).
- **Labels:** every labelled resource carries `app` and `env`.

## Not managed here

- The kill-switch function's code (`ops/budget-kill-switch`, deployed by its README command). Its
  budget, topic, account and permissions are managed here.
- Eventarc's Pub/Sub subscription settings (ack deadline 600 s, retry backoff): the subscription is
  owned by Eventarc and set by `ops/gcp/deploy-worker.sh`.
