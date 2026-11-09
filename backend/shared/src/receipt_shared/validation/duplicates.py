"""Duplicate detection.

- Same file bytes (SHA-256) as an earlier document          -> DUPLICATE
- Same merchant + same document number                      -> POSSIBLE_DUPLICATE (review)
- No document number: same merchant + date + total + currency -> POSSIBLE_DUPLICATE (review)
- Different document numbers                                -> never a duplicate

Identical-looking transactions are never auto-rejected: two coffees on the same day for the same
price can be real, so business-key matches go to human review instead.

Only documents created *before* the current one are considered (ties broken by document_id), so
two copies uploaded at the same moment cannot mark each other as duplicates. Rejected and failed
documents are ignored, so a user can re-upload something they rejected.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from datetime import datetime
from typing import Protocol

from receipt_shared.models.enums import DocumentStatus, DuplicateStatus
from receipt_shared.models.extraction import ExtractedDocument
from receipt_shared.models.validation import (
    DocumentFingerprint,
    Severity,
    ValidationCode,
    ValidationIssue,
)

IGNORED_STATUSES = frozenset({DocumentStatus.REJECTED.value, DocumentStatus.FAILED.value})
_NON_ALNUM = re.compile(r"[^0-9a-z]+")


def merchant_key(name: str | None) -> str | None:
    """'Café Nero, Ltd.' -> 'cafenero ltd' -> 'cafeneroltd' (accents, case, punctuation ignored)."""
    if not name:
        return None
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    key = _NON_ALNUM.sub("", ascii_name.casefold())
    return key or None


def document_number_key(number: str | None) -> str | None:
    """'INV-0042' and 'inv 42' -> 'INV42' (separators, case and leading zeros ignored)."""
    if not number:
        return None
    key = _NON_ALNUM.sub("", number.casefold()).upper()
    key = re.sub(r"(?<![0-9])0+(?=[0-9])", "", key)  # drop leading zeros of each number run
    return key or None


def fingerprint(
    *,
    document_id: str,
    user_id: str,
    file_sha256: str,
    document: ExtractedDocument | None,
    status: str,
    created_at: datetime,
) -> DocumentFingerprint:
    return DocumentFingerprint(
        document_id=document_id,
        user_id=user_id,
        file_sha256=file_sha256,
        merchant_key=merchant_key(document.merchant_name) if document else None,
        document_number_key=document_number_key(document.document_number) if document else None,
        document_date=document.document_date if document else None,
        total_amount=document.total_amount if document else None,
        currency=document.currency if document else None,
        status=status,
        created_at=created_at,
    )


class DuplicateIndex(Protocol):
    """Lookup of a user's earlier documents (Firestore in production)."""

    def candidates(
        self, *, user_id: str, file_sha256: str, merchant_key: str | None
    ) -> Iterable[DocumentFingerprint]:
        """Documents of ``user_id`` with the same file hash or the same merchant key."""
        ...


class InMemoryDuplicateIndex:
    """Simple index for tests and local runs."""

    def __init__(self, items: Iterable[DocumentFingerprint] = ()) -> None:
        self._items = list(items)

    def add(self, item: DocumentFingerprint) -> None:
        self._items.append(item)

    def candidates(
        self, *, user_id: str, file_sha256: str, merchant_key: str | None
    ) -> list[DocumentFingerprint]:
        return [
            f
            for f in self._items
            if f.user_id == user_id
            and (f.file_sha256 == file_sha256 or (merchant_key and f.merchant_key == merchant_key))
        ]


def _is_earlier(other: DocumentFingerprint, current: DocumentFingerprint) -> bool:
    return (other.created_at, other.document_id) < (current.created_at, current.document_id)


def _same_business_document(a: DocumentFingerprint, b: DocumentFingerprint) -> bool:
    if not a.merchant_key or a.merchant_key != b.merchant_key:
        return False
    if a.document_number_key and b.document_number_key:
        return a.document_number_key == b.document_number_key
    # At most one side has a number: fall back to the full business key.
    return (
        a.document_date is not None
        and a.document_date == b.document_date
        and a.total_amount is not None
        and b.total_amount is not None
        and a.total_amount == b.total_amount
        and a.currency == b.currency
    )


def check_duplicates(
    current: DocumentFingerprint, index: DuplicateIndex
) -> tuple[DuplicateStatus, list[str], list[ValidationIssue]]:
    candidates = [
        c
        for c in index.candidates(
            user_id=current.user_id,
            file_sha256=current.file_sha256,
            merchant_key=current.merchant_key,
        )
        if c.document_id != current.document_id
        and c.user_id == current.user_id
        and c.status not in IGNORED_STATUSES
        and _is_earlier(c, current)
    ]

    same_file = sorted({c.document_id for c in candidates if c.file_sha256 == current.file_sha256})
    if same_file:
        return (
            DuplicateStatus.DUPLICATE,
            same_file,
            [
                ValidationIssue(
                    code=ValidationCode.DUPLICATE_FILE,
                    severity=Severity.ERROR,
                    message="This exact file was already uploaded.",
                )
            ],
        )

    lookalikes = sorted({c.document_id for c in candidates if _same_business_document(current, c)})
    if lookalikes:
        return (
            DuplicateStatus.POSSIBLE_DUPLICATE,
            lookalikes,
            [
                ValidationIssue(
                    code=ValidationCode.POSSIBLE_DUPLICATE,
                    severity=Severity.ERROR,
                    message=(
                        "This looks like a document you already uploaded (same merchant and "
                        + (
                            "document number"
                            if current.document_number_key
                            else "date, total and currency"
                        )
                        + "). Confirm it is a separate transaction before approving."
                    ),
                    fields=["merchant_name", "document_number", "document_date", "total_amount"],
                )
            ],
        )
    return DuplicateStatus.NOT_DUPLICATE, [], []
