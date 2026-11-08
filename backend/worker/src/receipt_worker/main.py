"""FastAPI application factory for the processing worker.

The worker is invoked by Eventarc (CloudEvents over HTTP) and is not publicly reachable.
The CloudEvents receiver and processing pipeline are added in Phase 5.
"""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime
from importlib.metadata import version

from fastapi import FastAPI

from receipt_shared.config import Settings, get_settings
from receipt_shared.http import request_context_middleware
from receipt_shared.logging import configure_logging
from receipt_shared.models import HealthResponse

logger = logging.getLogger("receipt.worker")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging("worker", settings.log_level)

    app = FastAPI(
        title="Receipt & Invoice Extractor Worker",
        version=version("receipt-worker"),
        # The worker is internal; keep the schema available for local debugging only.
        docs_url="/docs" if settings.environment.value == "local" else None,
        redoc_url=None,
    )
    app.middleware("http")(request_context_middleware)

    @app.get("/health", response_model=HealthResponse, tags=["health"])
    def health() -> HealthResponse:
        return HealthResponse(
            service="worker",
            version=version("receipt-worker"),
            environment=settings.environment.value,
            timestamp=datetime.now(UTC),
        )

    logger.info("worker started", extra={"environment": settings.environment.value})
    return app


app = create_app()


def run() -> None:
    """Console entry point: ``uv run receipt-worker``."""
    import uvicorn

    uvicorn.run(
        "receipt_worker.main:app",
        host=os.environ.get("HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", "8081")),
        reload=os.environ.get("RELOAD", "").lower() in {"1", "true"},
        log_config=None,
        access_log=False,  # our middleware emits structured access logs (path only)
    )
