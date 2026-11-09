"""Gemini (Vertex AI) extraction client with timeouts, retries and structured logging.

Retries: transient failures (HTTP 408/429/500/502/503/504, network timeouts, connection errors,
an empty or non-JSON answer) are retried with exponential backoff and full jitter, honoring a
server ``Retry-After`` header when present. Permanent failures (4xx, blocked or truncated
answers) are raised immediately.

Logs carry identifiers and metrics only — never document contents or extracted values.
"""

from __future__ import annotations

import json
import logging
import random
import time
from collections.abc import Callable
from typing import Any, Protocol

from google import genai
from google.genai import errors as genai_errors
from google.genai import types
from pydantic import ValidationError

from receipt_shared.config import Settings, get_settings
from receipt_shared.extraction.documents import DocumentInput
from receipt_shared.extraction.errors import (
    ExtractionConfigError,
    ModelCallError,
    ModelResponseError,
    ModelTimeoutError,
    RateLimitedError,
)
from receipt_shared.extraction.prompt import PROMPT_VERSION, SYSTEM_INSTRUCTION, USER_INSTRUCTION
from receipt_shared.extraction.schema import GeminiExtraction, to_domain
from receipt_shared.models.extraction import ExtractionMetadata, ExtractionResult

logger = logging.getLogger("receipt.extraction")

RETRYABLE_STATUS_CODES = frozenset({408, 429, 500, 502, 503, 504})
# Finish reasons that mean the answer is unusable and retrying will not help.
_BLOCKED_FINISH_REASONS = frozenset(
    {"SAFETY", "RECITATION", "BLOCKLIST", "PROHIBITED_CONTENT", "SPII", "IMAGE_SAFETY"}
)


def _transient_network_errors() -> tuple[type[BaseException], ...]:
    """Timeout/connection exceptions from whichever HTTP stack the SDK uses (httpx or httpx2)."""
    found: list[type[BaseException]] = [TimeoutError, ConnectionError]
    for module_name in ("httpx", "httpx2"):
        try:
            module = __import__(module_name)
        except ImportError:  # pragma: no cover - depends on installed SDK extras
            continue
        for attr in ("TimeoutException", "ConnectError", "RemoteProtocolError"):
            cls = getattr(module, attr, None)
            if isinstance(cls, type) and issubclass(cls, BaseException):
                found.append(cls)
    return tuple(found)


_NETWORK_ERRORS = _transient_network_errors()


def _is_timeout(exc: BaseException) -> bool:
    return isinstance(exc, TimeoutError) or "Timeout" in type(exc).__name__


class _Models(Protocol):
    def generate_content(self, *, model: str, contents: Any, config: Any) -> Any: ...


class GenAIClient(Protocol):
    """The subset of ``google.genai.Client`` we use (lets tests inject a fake)."""

    @property
    def models(self) -> _Models: ...


def build_client(settings: Settings) -> genai.Client:
    """Create a Vertex AI Gen AI client. Credentials come from Application Default Credentials."""
    if not settings.gcp_project_id:
        raise ExtractionConfigError(
            "GCP_PROJECT_ID is not set; it is required to call Gemini through Vertex AI."
        )
    return genai.Client(
        vertexai=True,
        project=settings.gcp_project_id,
        location=settings.gemini_location,
        http_options=types.HttpOptions(
            timeout=int(settings.gemini_timeout_seconds * 1000),  # milliseconds
            # SDK-level retries disabled: this module owns retry policy, counting and logging.
            retry_options=None,
        ),
    )


class GeminiExtractor:
    """Extract structured data from one document with Gemini."""

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        client: GenAIClient | None = None,
        sleep: Callable[[float], None] = time.sleep,
        rng: Callable[[], float] = random.random,
    ) -> None:
        self._settings = settings or get_settings()
        self._client: GenAIClient = client or build_client(self._settings)
        self._sleep = sleep
        self._rng = rng

    @property
    def model(self) -> str:
        return self._settings.gemini_model

    def _config(self) -> types.GenerateContentConfig:
        s = self._settings
        thinking = (
            types.ThinkingConfig(thinking_budget=s.gemini_thinking_budget)
            if s.gemini_thinking_budget is not None
            else None
        )
        return types.GenerateContentConfig(
            system_instruction=SYSTEM_INSTRUCTION,
            temperature=0.0,
            max_output_tokens=s.gemini_max_output_tokens,
            response_mime_type="application/json",
            response_schema=GeminiExtraction,
            thinking_config=thinking,
        )

    @staticmethod
    def _contents(document: DocumentInput) -> list[types.Part]:
        if document.gcs_uri:
            doc_part = types.Part.from_uri(file_uri=document.gcs_uri, mime_type=document.mime_type)
        else:
            doc_part = types.Part.from_bytes(data=document.data, mime_type=document.mime_type)
        # Document first, then the (fixed, trusted) instruction.
        return [doc_part, types.Part.from_text(text=USER_INSTRUCTION)]

    def _backoff(self, attempt: int, retry_after: float | None) -> float:
        s = self._settings
        cap = min(
            s.gemini_retry_max_delay_seconds, s.gemini_retry_initial_delay_seconds * 2.0**attempt
        )
        delay = self._rng() * cap  # full jitter
        if retry_after is not None:
            delay = max(delay, min(retry_after, s.gemini_retry_max_delay_seconds))
        return delay

    @staticmethod
    def _retry_after(exc: genai_errors.APIError) -> float | None:
        response = getattr(exc, "response", None)
        headers = getattr(response, "headers", None)
        if not headers:
            return None
        value = headers.get("retry-after") or headers.get("Retry-After")
        try:
            return float(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    def _parse(self, response: Any) -> GeminiExtraction:
        candidates = getattr(response, "candidates", None) or []
        finish = _finish_reason(response)
        if finish in _BLOCKED_FINISH_REASONS:
            raise ModelResponseError(f"Gemini declined to answer (finish_reason={finish}).")
        if finish == "MAX_TOKENS":
            raise ModelResponseError(
                "Gemini's answer was truncated (MAX_TOKENS); raise GEMINI_MAX_OUTPUT_TOKENS."
            )
        text = getattr(response, "text", None) if candidates else None
        if not text:
            raise _RetryableResponseError("Gemini returned an empty response.")
        try:
            return GeminiExtraction.model_validate(json.loads(text))
        except (json.JSONDecodeError, ValidationError) as exc:
            raise _RetryableResponseError(
                "Gemini returned JSON that does not match the schema."
            ) from exc

    def extract(
        self, document: DocumentInput, *, document_id: str | None = None
    ) -> ExtractionResult:
        s = self._settings
        max_attempts = s.gemini_max_retries + 1
        log_ctx: dict[str, Any] = {
            "document_id": document_id,
            "model": s.gemini_model,
            "mime_type": document.mime_type,
            "size_bytes": document.size_bytes,
            "page_count": document.page_count,
            "prompt_version": PROMPT_VERSION,
        }
        logger.info("gemini extraction started", extra=log_ctx)
        config = self._config()
        contents = self._contents(document)
        start = time.perf_counter()

        attempt = 0
        bad_answers = 0
        while True:
            attempt += 1
            attempt_start = time.perf_counter()
            retry_after: float | None = None
            try:
                response = self._client.models.generate_content(
                    model=s.gemini_model, contents=contents, config=config
                )
                raw = self._parse(response)
            except genai_errors.APIError as exc:
                status = exc.code
                retryable = status in RETRYABLE_STATUS_CODES
                error: Exception = (
                    RateLimitedError(
                        "Gemini rate limit or quota exceeded.", retryable=True, status_code=status
                    )
                    if status == 429
                    else ModelCallError(
                        f"Gemini API error (HTTP {status}, {exc.status}): {_api_reason(exc)}",
                        retryable=retryable,
                        status_code=status,
                    )
                )
                retry_after = self._retry_after(exc) if retryable else None
                cause: BaseException = exc
            except _NETWORK_ERRORS as exc:
                retryable = True
                error = (
                    ModelTimeoutError(
                        f"Gemini request timed out after {s.gemini_timeout_seconds:g}s.",
                        retryable=True,
                    )
                    if _is_timeout(exc)
                    else ModelCallError(
                        f"Network error calling Gemini: {type(exc).__name__}.", retryable=True
                    )
                )
                cause = exc
            except _RetryableResponseError as exc:
                bad_answers += 1
                # A malformed answer is retried once; repeating more rarely helps at temperature 0.
                retryable = bad_answers <= 1
                error = ModelResponseError(str(exc))
                cause = exc
            except ModelResponseError as exc:
                logger.warning(
                    "gemini extraction failed",
                    extra={
                        **log_ctx,
                        "attempt": attempt,
                        "error_code": exc.code,
                        "retryable": False,
                    },
                )
                raise
            else:
                return self._result(response, raw, document_id, attempt, start, log_ctx)

            attempt_ms = round((time.perf_counter() - attempt_start) * 1000, 1)
            will_retry = retryable and attempt < max_attempts
            logger.warning(
                "gemini attempt failed",
                extra={
                    **log_ctx,
                    "attempt": attempt,
                    "max_attempts": max_attempts,
                    "error_code": getattr(error, "code", "unknown"),
                    "status_code": getattr(error, "status_code", None),
                    "attempt_latency_ms": attempt_ms,
                    "will_retry": will_retry,
                },
            )
            if not will_retry:
                raise error from cause
            self._sleep(self._backoff(attempt - 1, retry_after))

    def _result(
        self,
        response: Any,
        raw: GeminiExtraction,
        document_id: str | None,
        attempts: int,
        start: float,
        log_ctx: dict[str, Any],
    ) -> ExtractionResult:
        document, warnings = to_domain(raw)
        usage = getattr(response, "usage_metadata", None)
        metadata = ExtractionMetadata(
            model=self._settings.gemini_model,
            model_version=getattr(response, "model_version", None),
            prompt_version=PROMPT_VERSION,
            location=self._settings.gemini_location,
            latency_ms=round((time.perf_counter() - start) * 1000, 1),
            attempts=attempts,
            prompt_tokens=getattr(usage, "prompt_token_count", None),
            output_tokens=getattr(usage, "candidates_token_count", None),
            thoughts_tokens=getattr(usage, "thoughts_token_count", None),
            total_tokens=getattr(usage, "total_token_count", None),
            finish_reason=_finish_reason(response),
        )
        logger.info(
            "gemini extraction completed",
            extra={
                **log_ctx,
                "model_version": metadata.model_version,
                "latency_ms": metadata.latency_ms,
                "attempts": attempts,
                "prompt_tokens": metadata.prompt_tokens,
                "output_tokens": metadata.output_tokens,
                "total_tokens": metadata.total_tokens,
                "line_item_count": len(document.line_items),
                "missing_field_count": len(document.missing_fields),
                "warning_count": len(warnings),
            },
        )
        return ExtractionResult(document=document, metadata=metadata, warnings=warnings)


class _RetryableResponseError(Exception):
    """Internal: the model answered with something unparseable; worth one more try."""


def _api_reason(exc: genai_errors.APIError) -> str:
    """Google's explanation for an API error (e.g. billing disabled, permission missing).

    This is service metadata, not document content, so it is safe to surface and log.
    """
    reasons: list[str] = []
    details = exc.details if isinstance(exc.details, dict) else {}
    for item in details.get("error", {}).get("details", []) or []:
        if isinstance(item, dict) and isinstance(item.get("reason"), str):
            reasons.append(item["reason"])
    message = " ".join((exc.message or "").split())[:300]
    prefix = f"[{', '.join(reasons)}] " if reasons else ""
    return f"{prefix}{message}".strip() or "no details"


def _finish_reason(response: Any) -> str | None:
    candidates = getattr(response, "candidates", None) or []
    if not candidates:
        return None
    reason = getattr(candidates[0], "finish_reason", None)
    if reason is None:
        return None
    return str(getattr(reason, "name", reason))
