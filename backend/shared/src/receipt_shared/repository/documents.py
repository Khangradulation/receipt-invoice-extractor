"""Document records: one Firestore document per uploaded file (``documents/{document_id}``).

The API creates the record when it issues an upload URL (AWAITING_UPLOAD). The worker claims it
when the object-finalized event arrives and records every processing step. The original Gemini
output (``extraction``) is written once and never modified; reviewer corrections (Phase 9) are
stored separately.
"""

from __future__ import annotations

import base64
import copy
import json
import threading
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field

from receipt_shared.models.enums import (
    IN_PROGRESS_STATUSES,
    PROCESSING_DONE_STATUSES,
    DocumentStatus,
)


def _now() -> datetime:
    return datetime.now(UTC)


class DocumentRecord(BaseModel):
    model_config = ConfigDict(extra="allow")

    document_id: str
    user_id: str
    status: DocumentStatus
    original_filename: str
    bucket: str
    object_name: str
    content_type: str
    size_bytes: int
    client_sha256: str | None = None
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)
    upload_url_expires_at: datetime | None = None

    # --- processing (worker) ---
    object_generation: int | None = None
    file_sha256: str | None = None
    page_count: int | None = None
    processing_attempts: int = 0
    lease_expires_at: datetime | None = None
    uploaded_at: datetime | None = None
    processing_started_at: datetime | None = None
    extracted_at: datetime | None = None
    completed_at: datetime | None = None
    processing_duration_ms: float | None = None
    last_error: dict[str, Any] | None = None
    model_version: str | None = None
    analytics_loaded_at: datetime | None = None
    # Original AI output (never overwritten) and validation result, stored as JSON-safe dicts.
    extraction: dict[str, Any] | None = None
    validation: dict[str, Any] | None = None
    # Duplicate-detection fingerprint (strings so they are exact in Firestore).
    merchant_key: str | None = None
    document_number_key: str | None = None
    document_date: str | None = None
    total_amount: str | None = None
    currency: str | None = None
    history: list[dict[str, Any]] = Field(default_factory=list)

    def to_firestore(self) -> dict[str, Any]:
        return self.model_dump(mode="python")

    @classmethod
    def from_firestore(cls, data: dict[str, Any]) -> DocumentRecord:
        return cls.model_validate(data)


def history_entry(
    status: DocumentStatus, at: datetime, detail: str | None = None
) -> dict[str, Any]:
    entry: dict[str, Any] = {"status": status.value, "at": at}
    if detail:
        entry["detail"] = detail
    return entry


# --- claiming ----------------------------------------------------------------------------------
class ClaimOutcome(StrEnum):
    CLAIMED = "claimed"  # this delivery must process the document
    UNKNOWN_DOCUMENT = "unknown_document"  # no record: not uploaded through the API
    OBJECT_MISMATCH = "object_mismatch"  # event object does not belong to this record
    STALE_GENERATION = "stale_generation"  # a different upload of the same object was handled
    ALREADY_DONE = "already_done"  # duplicate event after processing finished
    IN_PROGRESS = "in_progress"  # another delivery holds a live lease
    GAVE_UP = "gave_up"  # too many attempts; marked FAILED


@dataclass(frozen=True)
class Claim:
    outcome: ClaimOutcome
    record: DocumentRecord | None = None


def decide_claim(
    record: DocumentRecord | None,
    *,
    object_name: str,
    generation: int,
    now: datetime,
    lease_seconds: int,
    max_attempts: int,
) -> tuple[ClaimOutcome, dict[str, Any], list[dict[str, Any]]]:
    """Pure claim decision: (outcome, field updates, history entries to append)."""
    if record is None:
        return ClaimOutcome.UNKNOWN_DOCUMENT, {}, []
    if record.object_name != object_name:
        return ClaimOutcome.OBJECT_MISMATCH, {}, []

    same_generation = record.object_generation == generation
    if record.object_generation is not None and not same_generation:
        if record.status is not DocumentStatus.FAILED:
            return ClaimOutcome.STALE_GENERATION, {}, []
    elif record.status in PROCESSING_DONE_STATUSES or record.status is DocumentStatus.FAILED:
        return ClaimOutcome.ALREADY_DONE, {}, []

    if (
        record.status in IN_PROGRESS_STATUSES
        and same_generation
        and record.lease_expires_at is not None
        and record.lease_expires_at > now
    ):
        return ClaimOutcome.IN_PROGRESS, {}, []

    attempts = record.processing_attempts + 1 if same_generation else 1
    if attempts > max_attempts:
        message = f"Processing failed {max_attempts} times; giving up."
        failed: dict[str, Any] = {
            "status": DocumentStatus.FAILED,
            "last_error": {
                "code": "too_many_attempts",
                "message": message,
                "retryable": False,
                "at": now,
            },
            "lease_expires_at": None,
            "completed_at": now,
        }
        return ClaimOutcome.GAVE_UP, failed, [history_entry(DocumentStatus.FAILED, now, message)]

    history: list[dict[str, Any]] = []
    updates: dict[str, Any] = {
        "status": DocumentStatus.PROCESSING,
        "object_generation": generation,
        "processing_attempts": attempts,
        "lease_expires_at": now + timedelta(seconds=lease_seconds),
    }
    if record.status is DocumentStatus.AWAITING_UPLOAD:
        updates["uploaded_at"] = now
        history.append(history_entry(DocumentStatus.UPLOADED, now))
    if record.processing_started_at is None or not same_generation:
        updates["processing_started_at"] = now
    history.append(history_entry(DocumentStatus.PROCESSING, now, f"attempt {attempts}"))
    return ClaimOutcome.CLAIMED, updates, history


# --- repositories ------------------------------------------------------------------------------
class DocumentAlreadyExistsError(RuntimeError):
    pass


class ConcurrentModificationError(RuntimeError):
    """The document changed after it was read (another tab, request or the worker)."""


def _same_instant(a: Any, b: datetime) -> bool:
    if not isinstance(a, datetime):
        return False
    left: datetime = a if a.tzinfo else a.replace(tzinfo=UTC)
    right = b if b.tzinfo else b.replace(tzinfo=UTC)
    return left == right


class DocumentRepository(Protocol):
    def create(self, record: DocumentRecord) -> None:
        """Insert a new record; raise ``DocumentAlreadyExistsError`` if the id is taken."""
        ...

    def get(self, document_id: str) -> DocumentRecord | None: ...

    def claim(
        self,
        document_id: str,
        *,
        object_name: str,
        generation: int,
        lease_seconds: int,
        max_attempts: int,
        now: datetime | None = None,
    ) -> Claim:
        """Atomically decide whether this event delivery should process the document."""
        ...

    def update(
        self,
        document_id: str,
        changes: dict[str, Any],
        *,
        history: Iterable[dict[str, Any]] = (),
    ) -> None:
        """Set top-level fields (and ``updated_at``) and append history entries."""
        ...

    def find_duplicate_candidates(
        self, *, user_id: str, file_sha256: str, merchant_key: str | None
    ) -> list[DocumentRecord]:
        """The user's documents with the same file hash or the same merchant key."""
        ...

    def update_if_unchanged(
        self,
        document_id: str,
        expected_updated_at: datetime,
        changes: dict[str, Any],
        *,
        history: Iterable[dict[str, Any]] = (),
    ) -> None:
        """Optimistic concurrency: apply ``changes`` only if nobody wrote since
        ``expected_updated_at``; otherwise raise ``ConcurrentModificationError``."""
        ...

    def list_for_user(
        self,
        user_id: str,
        *,
        statuses: list[DocumentStatus] | None = None,
        limit: int = 20,
        cursor: str | None = None,
    ) -> Page:
        """The user's documents, newest first, ``limit`` per page."""
        ...

    def delete(self, document_id: str) -> None:
        """Remove the record entirely (user deletion). Deleting a missing record is a no-op."""
        ...


@dataclass(frozen=True)
class Page:
    items: list[DocumentRecord]
    next_cursor: str | None


class InvalidCursorError(ValueError):
    pass


def encode_cursor(record: DocumentRecord) -> str:
    raw = json.dumps({"c": record.created_at.isoformat(), "d": record.document_id})
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")


def decode_cursor(cursor: str) -> tuple[datetime, str]:
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        data = json.loads(base64.urlsafe_b64decode(padded.encode()))
        created = datetime.fromisoformat(data["c"])
        doc_id = data["d"]
        if not isinstance(doc_id, str):
            raise TypeError
    except (ValueError, KeyError, TypeError) as exc:
        raise InvalidCursorError("invalid page cursor") from exc
    return created, doc_id


def _apply(
    data: dict[str, Any], changes: dict[str, Any], history: Iterable[dict[str, Any]], now: datetime
) -> None:
    data.update(copy.deepcopy(changes))
    data["updated_at"] = now
    data.setdefault("history", [])
    data["history"] = [*data["history"], *history]


class InMemoryDocumentRepository:
    def __init__(self) -> None:
        self._items: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    def create(self, record: DocumentRecord) -> None:
        with self._lock:
            if record.document_id in self._items:
                raise DocumentAlreadyExistsError(record.document_id)
            self._items[record.document_id] = copy.deepcopy(record.to_firestore())

    def get(self, document_id: str) -> DocumentRecord | None:
        data = self._items.get(document_id)
        return DocumentRecord.from_firestore(copy.deepcopy(data)) if data else None

    def claim(
        self,
        document_id: str,
        *,
        object_name: str,
        generation: int,
        lease_seconds: int,
        max_attempts: int,
        now: datetime | None = None,
    ) -> Claim:
        now = now or _now()
        with self._lock:
            data = self._items.get(document_id)
            record = DocumentRecord.from_firestore(copy.deepcopy(data)) if data else None
            outcome, changes, history = decide_claim(
                record,
                object_name=object_name,
                generation=generation,
                now=now,
                lease_seconds=lease_seconds,
                max_attempts=max_attempts,
            )
            if data is not None and changes:
                _apply(data, changes, history, now)
            updated = DocumentRecord.from_firestore(copy.deepcopy(data)) if data else None
        return Claim(outcome, updated)

    def update(
        self,
        document_id: str,
        changes: dict[str, Any],
        *,
        history: Iterable[dict[str, Any]] = (),
    ) -> None:
        with self._lock:
            _apply(self._items[document_id], changes, list(history), _now())

    def update_if_unchanged(
        self,
        document_id: str,
        expected_updated_at: datetime,
        changes: dict[str, Any],
        *,
        history: Iterable[dict[str, Any]] = (),
    ) -> None:
        with self._lock:
            data = self._items.get(document_id)
            if data is None or not _same_instant(data.get("updated_at"), expected_updated_at):
                raise ConcurrentModificationError(document_id)
            _apply(data, changes, list(history), _now())

    def find_duplicate_candidates(
        self, *, user_id: str, file_sha256: str, merchant_key: str | None
    ) -> list[DocumentRecord]:
        with self._lock:
            items = [copy.deepcopy(d) for d in self._items.values()]
        return [
            DocumentRecord.from_firestore(d)
            for d in items
            if d["user_id"] == user_id
            and (
                d.get("file_sha256") == file_sha256
                or (merchant_key is not None and d.get("merchant_key") == merchant_key)
            )
        ]

    def list_for_user(
        self,
        user_id: str,
        *,
        statuses: list[DocumentStatus] | None = None,
        limit: int = 20,
        cursor: str | None = None,
    ) -> Page:
        with self._lock:
            items = [copy.deepcopy(d) for d in self._items.values()]
        return _in_memory_list(items, user_id, statuses, limit, cursor)

    def delete(self, document_id: str) -> None:
        with self._lock:
            self._items.pop(document_id, None)


def _in_memory_list(
    items: list[dict[str, Any]],
    user_id: str,
    statuses: list[DocumentStatus] | None,
    limit: int,
    cursor: str | None,
) -> Page:
    wanted = {s.value for s in statuses} if statuses else None
    records = [
        DocumentRecord.from_firestore(d)
        for d in items
        if d["user_id"] == user_id
        and (wanted is None or getattr(d["status"], "value", d["status"]) in wanted)
    ]
    records.sort(key=lambda r: (r.created_at, r.document_id), reverse=True)
    if cursor:
        after = decode_cursor(cursor)
        records = [r for r in records if (r.created_at, r.document_id) < after]
    page = records[: limit + 1]
    has_more = len(page) > limit
    page = page[:limit]
    return Page(page, encode_cursor(page[-1]) if has_more and page else None)


class FirestoreDocumentRepository:
    def __init__(self, client: Any, collection: str = "documents") -> None:
        self._client = client
        self._collection = client.collection(collection)

    @classmethod
    def from_settings(cls, settings: Any) -> FirestoreDocumentRepository:
        from google.cloud import firestore

        client = firestore.Client(
            project=settings.gcp_project_id, database=settings.firestore_database
        )
        return cls(client, settings.firestore_documents_collection)

    def create(self, record: DocumentRecord) -> None:
        from google.api_core.exceptions import AlreadyExists

        try:
            self._collection.document(record.document_id).create(record.to_firestore())
        except AlreadyExists as exc:
            raise DocumentAlreadyExistsError(record.document_id) from exc

    def get(self, document_id: str) -> DocumentRecord | None:
        snapshot = self._collection.document(document_id).get()
        if not snapshot.exists:
            return None
        return DocumentRecord.from_firestore(snapshot.to_dict())

    def claim(
        self,
        document_id: str,
        *,
        object_name: str,
        generation: int,
        lease_seconds: int,
        max_attempts: int,
        now: datetime | None = None,
    ) -> Claim:
        from google.cloud import firestore

        ref = self._collection.document(document_id)

        @firestore.transactional
        def run(transaction: Any) -> Claim:
            snapshot = ref.get(transaction=transaction)
            record = DocumentRecord.from_firestore(snapshot.to_dict()) if snapshot.exists else None
            when = now or _now()
            outcome, changes, history = decide_claim(
                record,
                object_name=object_name,
                generation=generation,
                now=when,
                lease_seconds=lease_seconds,
                max_attempts=max_attempts,
            )
            if record is not None and changes:
                payload = dict(changes)
                payload["updated_at"] = when
                if history:
                    payload["history"] = firestore.ArrayUnion(history)
                transaction.update(ref, payload)
                merged = record.model_dump(mode="python") | changes
                merged["history"] = [*record.history, *history]
                record = DocumentRecord.from_firestore(merged)
            return Claim(outcome, record)

        result: Claim = run(self._client.transaction())
        return result

    def update(
        self,
        document_id: str,
        changes: dict[str, Any],
        *,
        history: Iterable[dict[str, Any]] = (),
    ) -> None:
        from google.cloud import firestore

        payload = dict(changes)
        payload["updated_at"] = _now()
        entries = list(history)
        if entries:
            payload["history"] = firestore.ArrayUnion(entries)
        self._collection.document(document_id).update(payload)

    def update_if_unchanged(
        self,
        document_id: str,
        expected_updated_at: datetime,
        changes: dict[str, Any],
        *,
        history: Iterable[dict[str, Any]] = (),
    ) -> None:
        from google.cloud import firestore

        ref = self._collection.document(document_id)
        entries = list(history)

        @firestore.transactional
        def run(transaction: Any) -> None:
            snapshot = ref.get(transaction=transaction)
            data = snapshot.to_dict() if snapshot.exists else None
            if data is None or not _same_instant(data.get("updated_at"), expected_updated_at):
                raise ConcurrentModificationError(document_id)
            payload = dict(changes)
            payload["updated_at"] = _now()
            if entries:
                payload["history"] = firestore.ArrayUnion(entries)
            transaction.update(ref, payload)

        run(self._client.transaction())

    def find_duplicate_candidates(
        self, *, user_id: str, file_sha256: str, merchant_key: str | None
    ) -> list[DocumentRecord]:
        from google.cloud.firestore_v1.base_query import FieldFilter

        found: dict[str, DocumentRecord] = {}
        queries = [("file_sha256", file_sha256)]
        if merchant_key:
            queries.append(("merchant_key", merchant_key))
        for field, value in queries:
            query = self._collection.where(filter=FieldFilter("user_id", "==", user_id)).where(
                filter=FieldFilter(field, "==", value)
            )
            for snapshot in query.stream():
                found[snapshot.id] = DocumentRecord.from_firestore(snapshot.to_dict())
        return list(found.values())

    def list_for_user(
        self,
        user_id: str,
        *,
        statuses: list[DocumentStatus] | None = None,
        limit: int = 20,
        cursor: str | None = None,
    ) -> Page:
        """Newest first. Needs composite indexes (user_id, [status,] created_at, document_id)."""
        from google.cloud import firestore
        from google.cloud.firestore_v1.base_query import FieldFilter

        query = self._collection.where(filter=FieldFilter("user_id", "==", user_id))
        if statuses:
            values = [s.value for s in statuses]
            query = (
                query.where(filter=FieldFilter("status", "==", values[0]))
                if len(values) == 1
                else query.where(filter=FieldFilter("status", "in", values))
            )
        query = query.order_by("created_at", direction=firestore.Query.DESCENDING).order_by(
            "document_id", direction=firestore.Query.DESCENDING
        )
        if cursor:
            created, doc_id = decode_cursor(cursor)
            query = query.start_after({"created_at": created, "document_id": doc_id})
        snapshots = list(query.limit(limit + 1).stream())
        records = [DocumentRecord.from_firestore(s.to_dict()) for s in snapshots[:limit]]
        has_more = len(snapshots) > limit
        return Page(records, encode_cursor(records[-1]) if has_more and records else None)

    def delete(self, document_id: str) -> None:
        self._collection.document(document_id).delete()


# --- duplicate index adapter -------------------------------------------------------------------
class RepositoryDuplicateIndex:
    """Exposes stored records as ``DocumentFingerprint``s for the validation engine."""

    def __init__(self, repository: DocumentRepository) -> None:
        self._repository = repository

    def candidates(self, *, user_id: str, file_sha256: str, merchant_key: str | None) -> list[Any]:
        from datetime import date
        from decimal import Decimal

        from receipt_shared.models.validation import DocumentFingerprint

        out = []
        for r in self._repository.find_duplicate_candidates(
            user_id=user_id, file_sha256=file_sha256, merchant_key=merchant_key
        ):
            if not r.file_sha256:
                continue  # not yet verified by the worker
            out.append(
                DocumentFingerprint(
                    document_id=r.document_id,
                    user_id=r.user_id,
                    file_sha256=r.file_sha256,
                    merchant_key=r.merchant_key,
                    document_number_key=r.document_number_key,
                    document_date=date.fromisoformat(r.document_date) if r.document_date else None,
                    total_amount=Decimal(r.total_amount) if r.total_amount else None,
                    currency=r.currency,
                    status=r.status.value,
                    created_at=r.created_at,
                )
            )
        return out
