"""Post-upload integrity checks (worker side; needs the ``[extraction]`` extra).

The upload URL already restricts content type and exact size. After the upload the worker
re-checks the bytes themselves: size, magic bytes vs. the declared type, PDF/image integrity,
page and pixel limits (``inspect_document``), and — if the client supplied one — the SHA-256.
"""

from __future__ import annotations

import hmac

from receipt_shared.config import Settings
from receipt_shared.extraction.documents import DocumentInput, inspect_document
from receipt_shared.extraction.errors import InvalidDocumentError
from receipt_shared.storage.gcs import StoredObject


class IntegrityError(InvalidDocumentError):
    code = "integrity_check_failed"


def verify_upload(
    obj: StoredObject,
    settings: Settings,
    *,
    expected_content_type: str,
    expected_size: int,
    expected_sha256: str | None = None,
    filename: str | None = None,
) -> DocumentInput:
    if obj.size != expected_size or len(obj.data) != expected_size:
        raise IntegrityError(
            f"Uploaded file is {len(obj.data)} bytes; {expected_size} bytes were declared."
        )
    document = inspect_document(
        obj.data,
        settings,
        filename=filename,
        declared_mime_type=expected_content_type,
        gcs_uri=obj.gcs_uri,
    )
    if expected_sha256 and not hmac.compare_digest(
        document.sha256, expected_sha256.strip().lower()
    ):
        raise IntegrityError("Uploaded file does not match the checksum provided at upload time.")
    return document
