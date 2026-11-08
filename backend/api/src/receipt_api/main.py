"""FastAPI application factory for the public API service."""

from __future__ import annotations

import logging
import os
from importlib.metadata import version

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from receipt_api.routers import health
from receipt_shared.config import Settings, get_settings
from receipt_shared.http import ErrorBody, ErrorResponse, request_context_middleware
from receipt_shared.logging import configure_logging

logger = logging.getLogger("receipt.api")

API_PREFIX = "/api/v1"


def _error(request: Request, status: int, code: str, message: str) -> JSONResponse:
    body = ErrorResponse(
        error=ErrorBody(
            code=code, message=message, request_id=getattr(request.state, "request_id", None)
        )
    )
    return JSONResponse(status_code=status, content=body.model_dump())


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging("api", settings.log_level)

    app = FastAPI(
        title="Receipt & Invoice Extractor API",
        version=version("receipt-api"),
        docs_url=f"{API_PREFIX}/docs",
        redoc_url=f"{API_PREFIX}/redoc",
        openapi_url=f"{API_PREFIX}/openapi.json",
        responses={500: {"model": ErrorResponse}},
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allowed_origins,
        allow_credentials=False,  # bearer tokens, not cookies
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
        expose_headers=["X-Request-ID"],
    )
    app.middleware("http")(request_context_middleware)

    @app.exception_handler(StarletteHTTPException)
    async def _http_exc(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = "not_found" if exc.status_code == 404 else f"http_{exc.status_code}"
        return _error(request, exc.status_code, code, str(exc.detail))

    @app.exception_handler(RequestValidationError)
    async def _validation_exc(request: Request, exc: RequestValidationError) -> JSONResponse:
        # Field locations and messages only; never echo submitted values back into logs.
        details = "; ".join(
            f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors()
        )
        return _error(request, 422, "validation_error", details)

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        logger.exception(
            "unhandled error", extra={"request_id": getattr(request.state, "request_id", None)}
        )
        return _error(request, 500, "internal_error", "An unexpected error occurred.")

    app.include_router(health.router, prefix=API_PREFIX)
    logger.info("api started", extra={"environment": settings.environment.value})
    return app


app = create_app()


def run() -> None:
    """Console entry point: ``uv run receipt-api``."""
    import uvicorn

    uvicorn.run(
        "receipt_api.main:app",
        host=os.environ.get("HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", "8080")),
        reload=os.environ.get("RELOAD", "").lower() in {"1", "true"},
        log_config=None,
        access_log=False,  # our middleware emits structured access logs (path only)
    )
