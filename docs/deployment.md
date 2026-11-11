# Deployment (GitHub Actions)

Three workflows in [`.github/workflows`](../.github/workflows):

| Workflow | Runs on | Does |
| --- | --- | --- |
| `ci.yml` | every pull request (and called by both deploy workflows) | backend lint/format/types/tests, frontend lint/format/types/tests/build, `pip-audit` + `npm audit`, `terraform fmt`/`validate`, Docker builds of all three images. No cloud credentials. |
| `deploy-dev.yml` | push to `main` (or run manually) | CI → build and push `api`, `worker`, `frontend` images tagged with the commit (`abc1234`) → `gcloud run deploy` each → smoke test |
| `deploy-prod.yml` | push of a version tag `vX.Y.Z` | CI → one job in the protected `production` environment: `terraform plan` + `apply`, build and push images tagged `vX.Y.Z`, deploy, smoke test |

## Authentication (no keys)

GitHub Actions signs in to Google Cloud with **Workload Identity Federation**: GitHub issues a
short-lived OIDC token, Google exchanges it for a short-lived access token. No service account key
exists anywhere.

- The pool's provider only accepts tokens from this repository.
- The CI accounts can only be used by jobs running in one **GitHub environment**: `dev` for the dev
  project, `production` for prod. The environment's deployment rules (branch `main` for dev, version
  tags and required reviewers for production) therefore decide who can deploy.
- Pull request CI has no `id-token` permission and no environment, so it can never get credentials.

| Account | Can | Used by |
| --- | --- | --- |
| `receipt-ci-deployer` | push images to Artifact Registry, deploy Cloud Run revisions as the three runtime accounts (`roles/run.developer` + `actAs`) | deploy-dev, deploy-prod |
| `receipt-ci-terraform` (prod only) | manage the resources in `modules/stack` | deploy-prod's Terraform step |

## Who owns what

Terraform creates the Cloud Run services and owns their settings (env vars, scaling, service
account, ingress). It creates them with Google's public placeholder image
(`us-docker.pkg.dev/cloudrun/container/hello`) and ignores image changes afterwards. The deploy
workflows only change the image. So a deploy never undoes a Terraform setting, and Terraform never
rolls back a deploy.

The web app is built with the API's address compiled in. Cloud Run URLs are predictable
(`https://SERVICE-PROJECT_NUMBER.REGION.run.app`), so Terraform adds the frontend's URL to the
bucket CORS, the API's CORS and Firebase's authorised domains on the first apply.

## Smoke test

[`ops/ci/smoke-test.sh`](../ops/ci/smoke-test.sh) (or `make smoke-test PROJECT_ID=...`) is
read-only and costs nothing beyond a few requests. It checks:

- all three services are ready, serve their newest revision, and run the expected image tag;
- the API's `/api/v1/health` responds, and `/api/v1/documents` returns 401 without a token;
- the frontend serves the app shell with its security headers, and deep links work;
- the worker can't be reached from the internet.

It doesn't upload a document. `make test-pipeline-live` does that (a few cents of Gemini calls).

## GitHub configuration

Each environment holds the same variable names (**Variables**, not Secrets: none of these values
are secret; the Firebase web API key is public by design and protected by authorised domains).

| Variable | dev | production |
| --- | --- | --- |
| `GCP_PROJECT_ID`, `GCP_PROJECT_NUMBER`, `GCP_REGION` | ✓ | ✓ |
| `GCP_WIF_PROVIDER`, `GCP_DEPLOYER_SA` (Terraform outputs) | ✓ | ✓ |
| `VITE_FIREBASE_API_KEY`, `VITE_FIREBASE_AUTH_DOMAIN`, `VITE_FIREBASE_APP_ID` | ✓ | ✓ |
| `GCP_TERRAFORM_SA`, `TF_STATE_BUCKET`, `GCP_BILLING_ACCOUNT`, `BUDGET_AMOUNT` | | ✓ |
| `WEB_ORIGINS`, `AUTH_DOMAINS`, `NOTIFICATION_CHANNELS` (optional HCL lists) | | ✓ |

Environment rules:

- `dev`: deployment branches limited to `main`.
- `production`: deployment limited to tags matching `v*`, with required reviewers. (Required
  reviewers on a private repository need a paid GitHub plan. Without them, the tag rule is the
  only gate.)

## Deploying

- **Dev:** merge to `main`. Watch it under Actions → Deploy dev.
- **Prod:** `git tag v1.0.0 && git push origin v1.0.0`, then approve the deployment.
- **Roll back:** redeploy an earlier image, e.g.
  `gcloud run deploy receipt-api --image .../api:<older-tag> --region us-central1`, or push a new tag
  from an earlier commit.

## Production bootstrap (one time)

The prod workflow's accounts are themselves created by Terraform, so the first apply is done by
a person with Owner on the new prod project:

1. Create the project, link billing, then run
   `PROJECT_ID=<prod> ./ops/gcp/bootstrap-tfstate.sh`.
2. `cd terraform/environments/prod`, create `terraform.tfvars` from the example,
   `terraform init -backend-config="bucket=<prod>-tfstate"`, `terraform plan`, `terraform apply`.
3. Grant the `ci_terraform_email` output `roles/billing.costsManager` on the billing account (the
   budget lives there, outside the project).
4. Enable Firebase Authentication email/password for the project and copy its web config.
5. Create the `production` GitHub environment and its variables (above). From then on, releases go
   through `deploy-prod.yml` only.
