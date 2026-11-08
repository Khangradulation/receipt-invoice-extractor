# syntax=docker/dockerfile:1
# Build from the backend/ directory:  docker build -f worker/Dockerfile -t receipt-worker .
ARG PYTHON_VERSION=3.12

FROM python:${PYTHON_VERSION}-slim AS builder
COPY --from=ghcr.io/astral-sh/uv:0.13.6 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv
WORKDIR /src

# 1) Third-party dependencies only (cached unless the lockfile changes)
COPY pyproject.toml uv.lock .python-version ./
COPY shared/pyproject.toml shared/
COPY api/pyproject.toml api/
COPY worker/pyproject.toml worker/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-workspace --package receipt-worker

# 2) Workspace packages, installed as regular (non-editable) wheels
COPY shared/ shared/
COPY worker/ worker/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-editable --package receipt-worker

FROM python:${PYTHON_VERSION}-slim AS runtime
RUN groupadd --system app && useradd --system --gid app --no-create-home app
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8080
USER app
EXPOSE 8080
# Cloud Run injects PORT; bind on all interfaces inside the container.
# Access logs come from our own middleware (structured JSON), so uvicorn's are disabled.
CMD ["sh", "-c", "exec uvicorn receipt_worker.main:app --host 0.0.0.0 --port ${PORT} --no-access-log --proxy-headers --forwarded-allow-ips=*"]
