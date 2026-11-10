"""FastAPI application factory for the public API service."""

from __future__ import annotations

import logging
import os
from collections.abc import Mapping
from importlib.metadata import version

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from receipt_api.review_service import ReviewError
from receipt_api.routers import analytics, documents, health, review
from receipt_shared.analytics import AnalyticsWriteError
from receipt_shared.config import Settings, get_settings
from receipt_shared.http import ErrorBody, ErrorResponse, request_context_middleware
from receipt_shared.logging import configure_logging

logger = logging.getLogger("receipt.api")

API_PREFIX = "/api/v1"


_ERROR_CODES = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    413: "file_too_large",
    415: "unsupported_file_type",
    429: "rate_limited",
    503: "service_unavailable",
}


def _error(
    request: Request,
    status: int,
    code: str,
    message: str,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    body = ErrorResponse(
        error=ErrorBody(
            code=code, message=message, request_id=getattr(request.state, "request_id", None)
        )
    )
    return JSONResponse(status_code=status, content=body.model_dump(), headers=headers)


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
        code = _ERROR_CODES.get(exc.status_code, f"http_{exc.status_code}")
        return _error(request, exc.status_code, code, str(exc.detail), exc.headers)

    @app.exception_handler(RequestValidationError)
    async def _validation_exc(request: Request, exc: RequestValidationError) -> JSONResponse:
        # Field locations and messages only; never echo submitted values back into logs.
        details = "; ".join(
            f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors()
        )
        return _error(request, 422, "validation_error", details)

    @app.exception_handler(ReviewError)
    async def _review_exc(request: Request, exc: ReviewError) -> JSONResponse:
        codes = {409: "conflict", 422: "invalid_correction"}
        response = _error(
            request, exc.status_code, codes.get(exc.status_code, "bad_request"), exc.message
        )
        if exc.validation is not None:
            import json as _json

            body = _json.loads(bytes(response.body))
            body["validation"] = exc.validation.model_dump(mode="json")
            return JSONResponse(status_code=exc.status_code, content=body)
        return response

    @app.exception_handler(AnalyticsWriteError)
    async def _analytics_exc(request: Request, exc: AnalyticsWriteError) -> JSONResponse:
        logger.error("analytics write failed during review", extra={"retryable": exc.retryable})
        return _error(
            request, 503, "service_unavailable", "Could not save to analytics. Please try again."
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        logger.exception(
            "unhandled error", extra={"request_id": getattr(request.state, "request_id", None)}
        )
        return _error(request, 500, "internal_error", "An unexpected error occurred.")

    app.state.settings = settings
    app.include_router(health.router, prefix=API_PREFIX)
    app.include_router(documents.router, prefix=API_PREFIX)
    app.include_router(review.router, prefix=API_PREFIX)
    app.include_router(analytics.router, prefix=API_PREFIX)
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
