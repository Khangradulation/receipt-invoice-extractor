"""Extraction errors.

``retryable`` tells callers (e.g. the worker) whether trying again later can succeed:
permanent errors should mark the document FAILED; retryable ones should let the event redeliver.
Messages never contain document contents.
"""

from __future__ import annotations


class ExtractionError(Exception):
    code: str = "extraction_error"
    retryable: bool = False

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


# --- Input problems (permanent) -------------------------------------------------------------
class InvalidDocumentError(ExtractionError):
    """The file is not something we can process."""

    code = "invalid_document"


class UnsupportedFileTypeError(InvalidDocumentError):
    code = "unsupported_file_type"


class FileTooLargeError(InvalidDocumentError):
    code = "file_too_large"


class TooManyPagesError(InvalidDocumentError):
    code = "too_many_pages"


class CorruptDocumentError(InvalidDocumentError):
    code = "corrupt_document"


# --- Configuration (permanent until fixed) ---------------------------------------------------
class ExtractionConfigError(ExtractionError):
    code = "configuration_error"


# --- Model call problems ---------------------------------------------------------------------
class ModelCallError(ExtractionError):
    """Gemini call failed after all retries, or failed permanently."""

    code = "model_error"

    def __init__(self, message: str, *, retryable: bool, status_code: int | None = None) -> None:
        super().__init__(message)
        self.retryable = retryable
        self.status_code = status_code


class RateLimitedError(ModelCallError):
    code = "rate_limited"


class ModelTimeoutError(ModelCallError):
    code = "model_timeout"


class ModelResponseError(ExtractionError):
    """The model answered, but the answer is unusable (blocked, truncated, not valid JSON)."""

    code = "invalid_model_response"
