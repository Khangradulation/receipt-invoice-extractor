"""Gemini-based receipt & invoice extraction engine.

Independent of the API, worker and cloud infrastructure: give it bytes, get structured data.

    from receipt_shared.extraction import GeminiExtractor, inspect_document
    doc = inspect_document(pdf_bytes, settings, filename="receipt.pdf")
    result = GeminiExtractor(settings).extract(doc, document_id="abc")
"""

import warnings

# google-genai 3.0's types.py has docstrings with an invalid escape sequence, which Python reports
# as a SyntaxWarning every time the module is compiled (i.e. on each run when bytecode caching is
# disabled). It is harmless; silence exactly that message before the SDK is first imported.
warnings.filterwarnings("ignore", message=r"invalid escape sequence '\\/'", category=SyntaxWarning)

from receipt_shared.extraction.documents import (  # noqa: E402
    SUPPORTED_MIME_TYPES,
    DocumentInput,
    inspect_document,
    sniff_mime_type,
)
from receipt_shared.extraction.errors import (  # noqa: E402
    CorruptDocumentError,
    ExtractionConfigError,
    ExtractionError,
    FileTooLargeError,
    InvalidDocumentError,
    ModelCallError,
    ModelResponseError,
    ModelTimeoutError,
    RateLimitedError,
    TooManyPagesError,
    UnsupportedFileTypeError,
)
from receipt_shared.extraction.gemini import GeminiExtractor, build_client  # noqa: E402
from receipt_shared.extraction.prompt import PROMPT_VERSION  # noqa: E402

__all__ = [
    "PROMPT_VERSION",
    "SUPPORTED_MIME_TYPES",
    "CorruptDocumentError",
    "DocumentInput",
    "ExtractionConfigError",
    "ExtractionError",
    "FileTooLargeError",
    "GeminiExtractor",
    "InvalidDocumentError",
    "ModelCallError",
    "ModelResponseError",
    "ModelTimeoutError",
    "RateLimitedError",
    "TooManyPagesError",
    "UnsupportedFileTypeError",
    "build_client",
    "inspect_document",
    "sniff_mime_type",
]
