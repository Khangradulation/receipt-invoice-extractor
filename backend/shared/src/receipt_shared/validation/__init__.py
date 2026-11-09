"""Rule-based validation of extracted receipts and invoices (independent of Gemini and GCP).

from receipt_shared.validation import DocumentValidator
result = DocumentValidator().validate(doc, document_id=..., user_id=..., file_sha256=...)
"""

from receipt_shared.validation.config import (
    OPTIONAL_FIELDS,
    REQUIRED_FIELDS,
    ValidationConfig,
    minor_unit,
)
from receipt_shared.validation.duplicates import (
    DuplicateIndex,
    InMemoryDuplicateIndex,
    check_duplicates,
    document_number_key,
    fingerprint,
    merchant_key,
)
from receipt_shared.validation.engine import RULES_VERSION, DocumentValidator

__all__ = [
    "OPTIONAL_FIELDS",
    "REQUIRED_FIELDS",
    "RULES_VERSION",
    "DocumentValidator",
    "DuplicateIndex",
    "InMemoryDuplicateIndex",
    "ValidationConfig",
    "check_duplicates",
    "document_number_key",
    "fingerprint",
    "merchant_key",
    "minor_unit",
]
