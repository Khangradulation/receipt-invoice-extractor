# Common developer commands. Run `make help` for the list.
.DEFAULT_GOAL := help
BACKEND := backend
FRONTEND := frontend

.PHONY: help install api worker web check test lint format backend-check frontend-check docker-build samples extract test-gemini-live test-storage-live

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-16s %s\n", $$1, $$2}'

install: ## Install backend (uv) and frontend (npm) dependencies
	cd $(BACKEND) && uv sync
	cd $(FRONTEND) && npm ci

api: ## Run the API with auto-reload on :8080
	cd $(BACKEND) && RELOAD=1 uv run receipt-api

worker: ## Run the worker with auto-reload on :8081
	cd $(BACKEND) && RELOAD=1 uv run receipt-worker

web: ## Run the Vite dev server on :5173 (proxies /api to :8080)
	cd $(FRONTEND) && npm run dev

backend-check: ## Lint, format-check, type-check and test the backend
	cd $(BACKEND) && uv run ruff check . ../evaluation ../ops && uv run ruff format --check . ../evaluation ../ops && \
		uv run mypy shared/src api/src worker/src && uv run pytest && \
		uv run pytest -q ../ops/budget-kill-switch

frontend-check: ## Lint, format-check, type-check, test and build the frontend
	cd $(FRONTEND) && npm run lint && npm run format:check && npm run typecheck && npm test && npm run build

check: backend-check frontend-check ## Run every check (what CI runs)

test: ## Run backend and frontend unit tests
	cd $(BACKEND) && uv run pytest
	cd $(FRONTEND) && npm test

samples: ## Generate synthetic sample receipts/invoices (+ ground truth) in evaluation/samples/out
	cd $(BACKEND) && uv run python ../evaluation/samples/generate_samples.py

extract: ## Extract with Gemini (billable): make extract FILES="path/a.pdf path/b.png"
	cd $(BACKEND) && uv run receipt-extract $(abspath $(FILES))

test-gemini-live: samples ## Run live Gemini integration tests (billable; needs GCP_PROJECT_ID + ADC)
	cd $(BACKEND) && RUN_GEMINI_INTEGRATION=1 uv run pytest -m integration -v

test-storage-live: samples ## Live Cloud Storage + Firestore round trip (needs bucket + ADC)
	cd $(BACKEND) && RUN_GCP_INTEGRATION=1 uv run pytest -m integration -v shared/tests/integration/test_storage_live.py

format: ## Auto-format backend and frontend
	cd $(BACKEND) && uv run ruff format . ../evaluation ../ops && uv run ruff check --fix . ../evaluation ../ops
	cd $(FRONTEND) && npm run format

docker-build: ## Build all three production images (requires Docker BuildKit/buildx)
	docker build -f $(BACKEND)/api/Dockerfile -t receipt-api:local $(BACKEND)
	docker build -f $(BACKEND)/worker/Dockerfile -t receipt-worker:local $(BACKEND)
	docker build -t receipt-frontend:local $(FRONTEND)
