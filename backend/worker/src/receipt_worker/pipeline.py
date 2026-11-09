"""Processing pipeline: Cloud Storage object -> verify -> Gemini -> validate -> persist.

Delivery is at-least-once, so ``DocumentProcessor.handle`` is idempotent:

* The document is claimed in a Firestore transaction keyed by ``document_id`` + object
  ``generation`` (``DocumentRepository.claim``). Replays of a finished document are acknowledged
  without work; a replay while another delivery holds the lease gets 429, so Pub/Sub retries later.
* The Gemini output is stored once. If a retry follows a crash after extraction, the stored
  output is reused instead of calling Gemini again (no overwrite, no double cost).
* Permanent errors -> FAILED + HTTP 200 (stop retries). Transient errors -> HTTP 503 (Eventarc
  retries) until ``MAX_PROCESSING_ATTEMPTS``, after which the document is FAILED.

HTTP status semantics for Eventarc/Pub/Sub: any 2xx acknowledges the event; anything else is
redelivered with backoff.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

from receipt_shared.config import Settings
from receipt_shared.extraction.documents import DocumentInput
from receipt_shared.extraction.errors import (
    ExtractionConfigError,
    ExtractionError,
    InvalidDocumentError,
    ModelCallError,
    ModelResponseError,
)
from receipt_shared.models.enums import DocumentStatus, ProcessingOutcome
from receipt_shared.models.extraction import ExtractionResult
from receipt_shared.models.validation import ValidationResult
from receipt_shared.repository import (
    ClaimOutcome,
    DocumentRecord,
    DocumentRepository,
    RepositoryDuplicateIndex,
    history_entry,
)
from receipt_shared.storage import parse_upload_object_name
from receipt_shared.storage.gcs import ObjectTooLargeError, StoredObject
from receipt_shared.storage.verify import verify_upload
from receipt_shared.validation import RULES_VERSION, DocumentValidator
from receipt_shared.validation.duplicates import document_number_key, merchant_key
from receipt_worker.events import FINALIZED, StorageObjectEvent

logger = logging.getLogger("receipt.worker.pipeline")

_FINAL_STATUS = {
    ProcessingOutcome.VALID: DocumentStatus.VALID,
    ProcessingOutcome.REVIEW_REQUIRED: DocumentStatus.REVIEW_REQUIRED,
    ProcessingOutcome.DUPLICATE: DocumentStatus.DUPLICATE,
}


class ObjectReader(Protocol):
    def read(self, object_name: str, *, generation: int | None = None) -> StoredObject: ...


class Extractor(Protocol):
    def extract(
        self, document: DocumentInput, *, document_id: str | None = None
    ) -> ExtractionResult: ...


class ValidSink(Protocol):
    """Destination for VALID records (BigQuery, Phase 6)."""

    def load(self, record: DocumentRecord, extraction: ExtractionResult) -> None: ...


@dataclass(frozen=True)
class Outcome:
    http_status: int
    result: str
    document_id: str | None = None
    status: DocumentStatus | None = None


class _PermanentError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code, self.message = code, message


class _TransientError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code, self.message = code, message


def _now() -> datetime:
    return datetime.now(UTC)


class DocumentProcessor:
    def __init__(
        self,
        settings: Settings,
        *,
        repository: DocumentRepository,
        storage: ObjectReader,
        extractor_factory: Callable[[], Extractor],
        validator: DocumentValidator,
        sink: ValidSink | None = None,
    ) -> None:
        self._settings = settings
        self._repo = repository
        self._storage = storage
        self._extractor_factory = extractor_factory
        self._extractor: Extractor | None = None
        self._validator = validator
        self._sink = sink

    # -- entry point -------------------------------------------------------------------------
    def handle(self, event: StorageObjectEvent) -> Outcome:
        ctx: dict[str, Any] = {
            "event_id": event.id,
            "object_generation": event.generation,
        }
        if event.type != FINALIZED:
            logger.info("ignored event type", extra=ctx | {"event_type": event.type})
            return Outcome(200, "ignored_event_type")
        if event.bucket != self._settings.gcs_upload_bucket:
            logger.warning("ignored event from unexpected bucket", extra=ctx)
            return Outcome(200, "ignored_bucket")
        path = parse_upload_object_name(event.name)
        if path is None:
            logger.info("ignored non-upload object", extra=ctx)
            return Outcome(200, "ignored_object")

        ctx["document_id"] = path.document_id
        claim = self._repo.claim(
            path.document_id,
            object_name=event.name,
            generation=event.generation,
            lease_seconds=self._settings.worker_lease_seconds,
            max_attempts=self._settings.max_processing_attempts,
        )
        if claim.outcome is ClaimOutcome.IN_PROGRESS:
            logger.info("event redelivered while processing; retry later", extra=ctx)
            return Outcome(429, claim.outcome.value, path.document_id)
        if claim.outcome is not ClaimOutcome.CLAIMED:
            level = (
                logging.WARNING
                if claim.outcome
                in (
                    ClaimOutcome.UNKNOWN_DOCUMENT,
                    ClaimOutcome.OBJECT_MISMATCH,
                    ClaimOutcome.GAVE_UP,
                )
                else logging.INFO
            )
            logger.log(level, "event not processed", extra=ctx | {"claim": claim.outcome.value})
            status = claim.record.status if claim.record else None
            return Outcome(200, claim.outcome.value, path.document_id, status)

        record = claim.record
        if record is None:  # pragma: no cover - CLAIMED always carries the record
            return Outcome(500, "claim_without_record", path.document_id)
        ctx["attempt"] = record.processing_attempts
        logger.info("processing started", extra=ctx)
        return self._process(record, event, ctx)

    # -- steps -------------------------------------------------------------------------------
    def _process(
        self, record: DocumentRecord, event: StorageObjectEvent, ctx: dict[str, Any]
    ) -> Outcome:
        start = time.perf_counter()
        doc_id = record.document_id
        try:
            document = self._verify(record, event)
            extraction = self._extract(record, document, ctx)

            self._repo.update(
                doc_id,
                {"status": DocumentStatus.VALIDATING},
                history=[history_entry(DocumentStatus.VALIDATING, _now())],
            )
            validation = self._validator.validate(
                extraction.document,
                document_id=doc_id,
                user_id=record.user_id,
                file_sha256=document.sha256,
                created_at=record.created_at,
                extraction_warnings=extraction.warnings,
                duplicate_index=RepositoryDuplicateIndex(self._repo),
            )
            final = _FINAL_STATUS[validation.validation_status]
            if final is DocumentStatus.VALID and self._sink is not None:
                self._sink.load(record, extraction)

            now = _now()
            started = record.processing_started_at or now
            self._repo.update(
                doc_id,
                {
                    "status": final,
                    "validation": validation.model_dump(mode="json"),
                    "completed_at": now,
                    "processing_duration_ms": round((now - started).total_seconds() * 1000, 1),
                    "lease_expires_at": None,
                    "last_error": None,
                },
                history=[history_entry(final, now)],
            )
            logger.info(
                "processing completed",
                extra=ctx
                | {
                    "status": final.value,
                    "duration_ms": round((time.perf_counter() - start) * 1000, 1),
                    "error_count": len(validation.validation_errors),
                    "warning_count": len(validation.validation_warnings),
                    "duplicate_status": validation.duplicate_status.value,
                },
            )
            return Outcome(200, "processed", doc_id, final)

        except _PermanentError as exc:
            self._fail(record, exc.code, exc.message, ctx)
            return Outcome(200, "failed", doc_id, DocumentStatus.FAILED)
        except _TransientError as exc:
            return self._release(record, exc.code, exc.message, ctx)
        except Exception as exc:  # unexpected bug: retry, bounded by max attempts
            logger.exception("unexpected processing error", extra=ctx)
            return self._release(record, "internal_error", type(exc).__name__, ctx, status=500)

    def _verify(self, record: DocumentRecord, event: StorageObjectEvent) -> DocumentInput:
        try:
            obj = self._storage.read(record.object_name, generation=event.generation)
        except FileNotFoundError as exc:
            raise _PermanentError("object_missing", "The uploaded file no longer exists.") from exc
        except ObjectTooLargeError as exc:
            raise _PermanentError(
                "file_too_large", "The uploaded file exceeds the size limit."
            ) from exc
        try:
            document = verify_upload(
                obj,
                self._settings,
                expected_content_type=record.content_type,
                expected_size=record.size_bytes,
                expected_sha256=record.client_sha256,
                filename=record.original_filename,
            )
        except InvalidDocumentError as exc:
            raise _PermanentError(exc.code, exc.message) from exc
        # Recorded before extraction so concurrent uploads of the same file can see each other.
        self._repo.update(
            record.document_id,
            {"file_sha256": document.sha256, "page_count": document.page_count},
        )
        return document

    def _extract(
        self, record: DocumentRecord, document: DocumentInput, ctx: dict[str, Any]
    ) -> ExtractionResult:
        if record.extraction is not None:
            logger.info("reusing stored extraction", extra=ctx)
            return ExtractionResult.model_validate(record.extraction)

        if self._extractor is None:
            self._extractor = self._extractor_factory()
        try:
            result = self._extractor.extract(document, document_id=record.document_id)
        except ModelCallError as exc:
            if exc.retryable:
                raise _TransientError(exc.code, exc.message) from exc
            raise _PermanentError(exc.code, exc.message) from exc
        except ExtractionConfigError as exc:
            raise _TransientError(exc.code, exc.message) from exc  # fixable by redeploying
        except (ModelResponseError, InvalidDocumentError) as exc:
            raise _PermanentError(exc.code, exc.message) from exc
        except ExtractionError as exc:
            raise _PermanentError(exc.code, exc.message) from exc

        doc = result.document
        now = _now()
        self._repo.update(
            record.document_id,
            {
                "status": DocumentStatus.EXTRACTED,
                "extraction": result.model_dump(mode="json"),
                "extracted_at": now,
                "model_version": result.metadata.model_version or result.metadata.model,
                "merchant_key": merchant_key(doc.merchant_name),
                "document_number_key": document_number_key(doc.document_number),
                "document_date": doc.document_date.isoformat() if doc.document_date else None,
                "total_amount": str(doc.total_amount) if doc.total_amount is not None else None,
                "currency": doc.currency,
            },
            history=[history_entry(DocumentStatus.EXTRACTED, now)],
        )
        logger.info(
            "extraction stored",
            extra=ctx
            | {
                "model_version": result.metadata.model_version,
                "gemini_latency_ms": result.metadata.latency_ms,
                "gemini_attempts": result.metadata.attempts,
            },
        )
        return result

    # -- failure handling --------------------------------------------------------------------
    def _fail(self, record: DocumentRecord, code: str, message: str, ctx: dict[str, Any]) -> None:
        now = _now()
        result = ValidationResult.processing_failed(message, rules_version=RULES_VERSION)
        self._repo.update(
            record.document_id,
            {
                "status": DocumentStatus.FAILED,
                "last_error": {"code": code, "message": message, "retryable": False, "at": now},
                "validation": result.model_dump(mode="json"),
                "completed_at": now,
                "lease_expires_at": None,
            },
            history=[history_entry(DocumentStatus.FAILED, now, code)],
        )
        logger.warning("processing failed permanently", extra=ctx | {"error_code": code})

    def _release(
        self,
        record: DocumentRecord,
        code: str,
        message: str,
        ctx: dict[str, Any],
        *,
        status: int = 503,
    ) -> Outcome:
        """Record a transient failure and release the lease so the redelivery can claim it."""
        now = _now()
        self._repo.update(
            record.document_id,
            {
                "last_error": {"code": code, "message": message, "retryable": True, "at": now},
                "lease_expires_at": None,
            },
        )
        logger.warning(
            "processing attempt failed; will retry",
            extra=ctx
            | {"error_code": code, "max_attempts": self._settings.max_processing_attempts},
        )
        return Outcome(status, "retry", record.document_id, None)
