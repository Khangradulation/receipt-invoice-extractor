"""HTTP plumbing shared by the FastAPI services (request IDs, access logs, error model)."""

from __future__ import annotations

import logging
import re
import time
import uuid
from collections.abc import Awaitable, Callable

from pydantic import BaseModel
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger("receipt.http")

REQUEST_ID_HEADER = "X-Request-ID"
# Cloud Run sets this header; its trace ID ties our logs to the request log entry.
CLOUD_TRACE_HEADER = "X-Cloud-Trace-Context"
# Client-supplied request IDs are echoed into logs and headers, so only safe ones are kept.
_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,128}$")
_TRACE_ID_RE = re.compile(r"^[0-9a-fA-F]{32}$")


def safe_request_id(value: str | None) -> str:
    """The client's request ID if it is short and plain, otherwise a fresh one."""
    return value if value and _REQUEST_ID_RE.match(value) else uuid.uuid4().hex


class ErrorBody(BaseModel):
    code: str
    message: str
    request_id: str | None = None


class ErrorResponse(BaseModel):
    error: ErrorBody


async def request_context_middleware(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """Attach a request ID, time the request and emit one structured access log line."""
    request_id = safe_request_id(request.headers.get(REQUEST_ID_HEADER))
    request.state.request_id = request_id
    start = time.perf_counter()
    status = 500
    try:
        response = await call_next(request)
        status = response.status_code
        response.headers[REQUEST_ID_HEADER] = request_id
        return response
    finally:
        extra: dict[str, object] = {
            "request_id": request_id,
            "http_method": request.method,
            "http_path": request.url.path,  # path only: never log query strings
            "http_status": status,
            "duration_ms": round((time.perf_counter() - start) * 1000, 2),
        }
        trace = request.headers.get(CLOUD_TRACE_HEADER)
        trace_id = trace.split("/", 1)[0] if trace else ""
        if _TRACE_ID_RE.match(trace_id):
            extra["trace_id"] = trace_id
        logger.info("request completed", extra=extra)
