"""FastAPI application for the processing worker (invoked by Eventarc; not public)."""

from __future__ import annotations

import logging
import os
import threading
from datetime import UTC, datetime
from importlib.metadata import version

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

from receipt_shared.config import Settings, get_settings
from receipt_shared.http import request_context_middleware
from receipt_shared.logging import configure_logging
from receipt_shared.models import HealthResponse
from receipt_worker.events import InvalidEventError, parse_storage_event
from receipt_worker.pipeline import DocumentProcessor

logger = logging.getLogger("receipt.worker")
_lock = threading.Lock()


def build_processor(settings: Settings) -> DocumentProcessor:
    """Wire the real Firestore / Cloud Storage / Gemini implementations."""
    from receipt_shared.extraction import GeminiExtractor
    from receipt_shared.repository import FirestoreDocumentRepository
    from receipt_shared.storage import DocumentStorage
    from receipt_shared.validation import DocumentValidator

    return DocumentProcessor(
        settings,
        repository=FirestoreDocumentRepository.from_settings(settings),
        storage=DocumentStorage(settings),
        extractor_factory=lambda: GeminiExtractor(settings),
        validator=DocumentValidator(settings=settings),
        sink=None,  # BigQuery loading is added in Phase 6
    )


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging("worker", settings.log_level)

    app = FastAPI(
        title="Receipt & Invoice Extractor Worker",
        version=version("receipt-worker"),
        docs_url="/docs" if settings.environment.value == "local" else None,
        redoc_url=None,
    )
    app.state.settings = settings
    app.middleware("http")(request_context_middleware)

    def processor() -> DocumentProcessor:
        with _lock:
            proc: DocumentProcessor | None = getattr(app.state, "processor", None)
            if proc is None:
                proc = build_processor(settings)
                app.state.processor = proc
        return proc

    @app.get("/health", response_model=HealthResponse, tags=["health"])
    def health() -> HealthResponse:
        return HealthResponse(
            service="worker",
            version=version("receipt-worker"),
            environment=settings.environment.value,
            timestamp=datetime.now(UTC),
        )

    @app.post("/events/storage", tags=["events"])
    async def storage_event(request: Request) -> Response:
        body = await request.body()
        try:
            event = parse_storage_event(request.headers, body)
        except InvalidEventError as exc:
            # A malformed event can never succeed; acknowledge it (2xx) so it is not redelivered
            # forever, and log at ERROR so it is visible in monitoring.
            logger.error("malformed event ignored", extra={"reason": str(exc)})
            return JSONResponse({"result": "malformed_event"}, status_code=200)

        from starlette.concurrency import run_in_threadpool

        outcome = await run_in_threadpool(processor().handle, event)
        return JSONResponse(
            {
                "result": outcome.result,
                "document_id": outcome.document_id,
                "status": outcome.status.value if outcome.status else None,
            },
            status_code=outcome.http_status,
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
