"""User-initiated document deletion (the right to delete).

Order matters: the file (every stored version) goes first, then the analytics rows, and the
Firestore record last. If any step fails the record still exists, the user sees an error, and
retrying the delete finishes the job (every step is idempotent). Deleting the record last also
means a document never "disappears" from the app while its data still exists elsewhere.

Documents that may still be written to are refused (409) so nothing is recreated afterwards:
an upload URL that hasn't expired yet, or a worker that holds a live processing lease.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Protocol

from receipt_shared.models.enums import IN_PROGRESS_STATUSES, DocumentStatus
from receipt_shared.repository import DocumentRecord, DocumentRepository

logger = logging.getLogger("receipt.api.deletion")


class ObjectDeleter(Protocol):
    def delete_all_versions(self, object_name: str) -> int: ...


class RowDeleter(Protocol):
    def delete(self, document_id: str) -> None: ...


class DocumentBusyError(RuntimeError):
    """The document may still change (upload pending or processing); try again later."""


def busy_reason(record: DocumentRecord, now: datetime) -> str | None:
    if (
        record.status is DocumentStatus.AWAITING_UPLOAD
        and record.upload_url_expires_at is not None
        and _aware(record.upload_url_expires_at) > now
    ):
        return "The upload link for this document is still valid. Try again after it expires."
    if (
        record.status in IN_PROGRESS_STATUSES
        and record.lease_expires_at is not None
        and _aware(record.lease_expires_at) > now
    ):
        return "This document is being processed. Try again in a few minutes."
    return None


def delete_document(
    record: DocumentRecord,
    *,
    repository: DocumentRepository,
    storage: ObjectDeleter,
    analytics: RowDeleter,
    now: datetime | None = None,
) -> None:
    reason = busy_reason(record, now or datetime.now(UTC))
    if reason:
        raise DocumentBusyError(reason)
    versions = storage.delete_all_versions(record.object_name)
    analytics.delete(record.document_id)
    repository.delete(record.document_id)
    logger.info(
        "document deleted",
        extra={
            "document_id": record.document_id,
            "status": record.status.value,
            "file_versions_deleted": versions,
        },
    )


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)
