"""Manual review: corrections with an audit trail, revalidation, approval and rejection.

* The original Gemini output (``record.extraction``) is never modified. Reviewer corrections are
  stored separately in ``record.review.corrected``.
* Every changed field appends an audit entry: field, original AI value, previous value,
  corrected value, reviewer, timestamp.
* Approval re-runs validation on the corrected data and is refused while errors remain.
* Approval/rejection writes BigQuery first (approved transaction + review_records, atomically),
  then Firestore — same ordering as the worker, so the two stores can't drift.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Any, Protocol

from pydantic import ValidationError as PydanticValidationError

from receipt_shared.analytics import AnalyticsRows, build_rows
from receipt_shared.models.enums import DocumentStatus
from receipt_shared.models.extraction import (
    EXTRACTABLE_FIELDS,
    ExtractedDocument,
    ExtractionResult,
)
from receipt_shared.models.validation import ValidationResult
from receipt_shared.repository import (
    DocumentRecord,
    DocumentRepository,
    RepositoryDuplicateIndex,
    history_entry,
)
from receipt_shared.validation import DocumentValidator

logger = logging.getLogger("receipt.api.review")

EDITABLE_FIELDS: frozenset[str] = frozenset({*EXTRACTABLE_FIELDS, "line_items"})
REVIEWABLE = frozenset({DocumentStatus.REVIEW_REQUIRED})
REJECTABLE = frozenset({DocumentStatus.REVIEW_REQUIRED, DocumentStatus.DUPLICATE})


class AnalyticsWriter(Protocol):
    def write(self, rows: AnalyticsRows) -> None: ...


class ReviewError(Exception):
    """Base class; carries an HTTP status and a user-facing message."""

    status_code = 400

    def __init__(self, message: str, validation: ValidationResult | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.validation = validation


class NotReviewableError(ReviewError):
    status_code = 409


class InvalidCorrectionError(ReviewError):
    status_code = 422


class ApprovalBlockedError(ReviewError):
    status_code = 409


@dataclass(frozen=True)
class ReviewState:
    record: DocumentRecord
    original: ExtractedDocument | None
    corrected: ExtractedDocument | None
    validation: ValidationResult | None
    corrections: list[dict[str, Any]]
    duplicate_acknowledged: bool


def _now() -> datetime:
    return datetime.now(UTC)


def _review(record: DocumentRecord) -> dict[str, Any]:
    extra = record.model_extra or {}
    review = extra.get("review")
    return dict(review) if isinstance(review, dict) else {}


def _audit_value(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return json.dumps(value, separators=(",", ":"), sort_keys=True)


class ReviewService:
    def __init__(
        self,
        *,
        repository: DocumentRepository,
        validator: DocumentValidator,
        writer: AnalyticsWriter,
    ) -> None:
        self._repo = repository
        self._validator = validator
        self._writer = writer

    # -- reading -----------------------------------------------------------------------------
    @staticmethod
    def original(record: DocumentRecord) -> ExtractedDocument | None:
        if record.extraction is None:
            return None
        return ExtractionResult.model_validate(record.extraction).document

    def state(self, record: DocumentRecord) -> ReviewState:
        review = _review(record)
        corrected = (
            ExtractedDocument.model_validate(review["corrected"])
            if review.get("corrected")
            else None
        )
        validation_data = review.get("validation") or record.validation
        return ReviewState(
            record=record,
            original=self.original(record),
            corrected=corrected,
            validation=ValidationResult.model_validate(validation_data)
            if validation_data
            else None,
            corrections=list(review.get("corrections") or []),
            duplicate_acknowledged=bool(review.get("duplicate_acknowledged")),
        )

    def live_state(self, record: DocumentRecord) -> ReviewState:
        """Review state with validation re-run against the *current* rules and data.

        Used when opening a document for review, so rule changes (e.g. a newly supported
        currency) and newly arrived duplicates are reflected immediately. Nothing is persisted.
        """
        st = self.state(record)
        document = st.corrected or st.original
        if record.status not in REVIEWABLE or document is None:
            return st
        return replace(st, validation=self._validate(record, document, st.duplicate_acknowledged))

    def effective(self, record: DocumentRecord) -> ExtractedDocument | None:
        st = self.state(record)
        return st.corrected or st.original

    def _validate(
        self, record: DocumentRecord, document: ExtractedDocument, acknowledged: bool
    ) -> ValidationResult:
        return self._validator.validate(
            document,
            document_id=record.document_id,
            user_id=record.user_id,
            file_sha256=record.file_sha256 or "",
            created_at=record.created_at,
            duplicate_index=RepositoryDuplicateIndex(self._repo),
            duplicate_acknowledged=acknowledged,
        )

    # -- corrections -------------------------------------------------------------------------
    def save_corrections(
        self,
        record: DocumentRecord,
        *,
        reviewer_id: str,
        fields: dict[str, Any],
        acknowledge_duplicate: bool = False,
    ) -> ReviewState:
        if record.status not in REVIEWABLE:
            raise NotReviewableError(f"Document is {record.status.value}; it is not in review.")
        unknown = sorted(set(fields) - EDITABLE_FIELDS)
        if unknown:
            raise InvalidCorrectionError(f"These fields cannot be edited: {', '.join(unknown)}.")
        current = self.effective(record)
        if current is None:
            raise NotReviewableError("Document has no extracted data to correct.")
        original = self.original(record)

        current_json = current.model_dump(mode="json")
        try:
            updated = ExtractedDocument.model_validate({**current_json, **fields})
        except PydanticValidationError as exc:
            problems = "; ".join(
                f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors()
            )
            raise InvalidCorrectionError(f"Invalid correction: {problems}") from exc
        updated.missing_fields = [f for f in EXTRACTABLE_FIELDS if getattr(updated, f) is None]
        updated_json = updated.model_dump(mode="json")
        original_json = original.model_dump(mode="json") if original else {}

        st = self.state(record)
        now = _now()
        new_entries: list[dict[str, Any]] = []
        for name in sorted(fields):
            if updated_json.get(name) == current_json.get(name):
                continue
            sequence = len(st.corrections) + len(new_entries) + 1
            new_entries.append(
                {
                    "review_id": f"{record.document_id}:c{sequence}",
                    "action": "CORRECTION",
                    "field_name": name,
                    "original_value": _audit_value(original_json.get(name)),
                    "previous_value": _audit_value(current_json.get(name)),
                    "corrected_value": _audit_value(updated_json.get(name)),
                    "reviewer_id": reviewer_id,
                    "reviewed_at": now,
                }
            )

        acknowledged = acknowledge_duplicate or st.duplicate_acknowledged
        validation = self._validate(record, updated, acknowledged)
        review = {
            "corrected": updated_json,
            "corrections": [*st.corrections, *new_entries],
            "validation": validation.model_dump(mode="json"),
            "duplicate_acknowledged": acknowledged,
            "updated_at": now,
            "updated_by": reviewer_id,
        }
        self._repo.update(record.document_id, {"review": review})
        logger.info(
            "review corrections saved",
            extra={
                "document_id": record.document_id,
                "changed_fields": len(new_entries),
                "is_valid": validation.is_valid,
            },
        )
        refreshed = self._repo.get(record.document_id)
        return self.state(refreshed or record)

    # -- decisions ---------------------------------------------------------------------------
    def _review_rows(self, st: ReviewState, decision: dict[str, Any]) -> list[dict[str, Any]]:
        model_version = st.record.model_version
        rows = []
        for c in [*st.corrections, decision]:
            rows.append(
                {
                    "review_id": c["review_id"],
                    "document_id": st.record.document_id,
                    "user_id": st.record.user_id,
                    "action": c["action"],
                    "field_name": c.get("field_name"),
                    "original_value": c.get("original_value"),
                    "corrected_value": c.get("corrected_value"),
                    "reason": c.get("reason"),
                    "reviewer_id": c["reviewer_id"],
                    "model_version": model_version,
                    "reviewed_at": c["reviewed_at"],
                }
            )
        return rows

    def approve(self, record: DocumentRecord, *, reviewer_id: str) -> ReviewState:
        if record.status not in REVIEWABLE:
            raise NotReviewableError(f"Document is {record.status.value}; it cannot be approved.")
        st = self.state(record)
        document = st.corrected or st.original
        if document is None or record.extraction is None:
            raise NotReviewableError("Document has no extracted data to approve.")
        validation = self._validate(record, document, st.duplicate_acknowledged)
        if not validation.is_valid:
            raise ApprovalBlockedError(
                "Fix the remaining validation errors before approving.", validation
            )

        now = _now()
        decision = {
            "review_id": f"{record.document_id}:approve",
            "action": "APPROVE",
            "reviewer_id": reviewer_id,
            "reviewed_at": now,
        }
        rows = build_rows(
            record,
            status=DocumentStatus.APPROVED,
            extraction=ExtractionResult.model_validate(record.extraction),
            validation=validation,
            now=now,
            effective_document=document,
            record_source="REVIEWED",
            approved_by=reviewer_id,
            approved_at=now,
            review_required=True,
            review_records=self._review_rows(st, decision),
        )
        self._writer.write(rows)  # BigQuery first; raises -> nothing changes in Firestore
        review = _review(record) | {"validation": validation.model_dump(mode="json")}
        self._repo.update(
            record.document_id,
            {
                "status": DocumentStatus.APPROVED,
                "approved_by": reviewer_id,
                "approved_at": now,
                "review": review,
                "analytics_loaded_at": now,
            },
            history=[history_entry(DocumentStatus.APPROVED, now, f"by {reviewer_id}")],
        )
        logger.info("document approved", extra={"document_id": record.document_id})
        refreshed = self._repo.get(record.document_id)
        return self.state(refreshed or record)

    def reject(self, record: DocumentRecord, *, reviewer_id: str, reason: str) -> ReviewState:
        if record.status not in REJECTABLE:
            raise NotReviewableError(f"Document is {record.status.value}; it cannot be rejected.")
        st = self.state(record)
        now = _now()
        decision = {
            "review_id": f"{record.document_id}:reject",
            "action": "REJECT",
            "reason": reason,
            "reviewer_id": reviewer_id,
            "reviewed_at": now,
        }
        extraction = (
            ExtractionResult.model_validate(record.extraction) if record.extraction else None
        )
        rows = build_rows(
            record,
            status=DocumentStatus.REJECTED,
            extraction=extraction,
            validation=st.validation,
            now=now,
            review_required=record.status is DocumentStatus.REVIEW_REQUIRED,
            review_records=self._review_rows(st, decision),
        )
        self._writer.write(rows)
        self._repo.update(
            record.document_id,
            {
                "status": DocumentStatus.REJECTED,
                "rejected_by": reviewer_id,
                "rejected_at": now,
                "rejection_reason": reason,
                "analytics_loaded_at": now,
            },
            history=[history_entry(DocumentStatus.REJECTED, now, f"by {reviewer_id}")],
        )
        logger.info("document rejected", extra={"document_id": record.document_id})
        refreshed = self._repo.get(record.document_id)
        return self.state(refreshed or record)
