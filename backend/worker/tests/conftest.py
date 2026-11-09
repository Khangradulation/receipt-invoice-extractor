import io
from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from PIL import Image

from receipt_shared.config import Settings
from receipt_shared.extraction.documents import DocumentInput
from receipt_shared.extraction.errors import ExtractionError
from receipt_shared.models.enums import DocumentStatus
from receipt_shared.models.extraction import (
    ExtractedDocument,
    ExtractionMetadata,
    ExtractionResult,
    LineItem,
)
from receipt_shared.repository import DocumentRecord, InMemoryDocumentRepository
from receipt_shared.storage.gcs import StoredObject
from receipt_shared.validation import DocumentValidator, ValidationConfig
from receipt_worker.events import FINALIZED, StorageObjectEvent
from receipt_worker.pipeline import DocumentProcessor

BUCKET = "docs-bucket"
USER = "user_A"


def png(color: str = "white") -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (120, 160), color).save(buf, "PNG")
    return buf.getvalue()


def good_document(**overrides: Any) -> ExtractedDocument:
    base: dict[str, Any] = {
        "document_type": "receipt",
        "document_number": "R-1",
        "document_date": date(2026, 3, 14),
        "currency": "CAD",
        "merchant_name": "Maple Leaf Cafe",
        "merchant_address": "42 Harbour St",
        "subtotal": Decimal("23.20"),
        "tax_amount": Decimal("3.48"),
        "total_amount": Decimal("26.68"),
        "payment_method": "credit_card",
        "expense_category": "meals",
        "line_items": [
            LineItem(
                description="Lunch",
                quantity=Decimal(1),
                unit_price=Decimal("23.20"),
                total_price=Decimal("23.20"),
            )
        ],
    }
    return ExtractedDocument(**(base | overrides))


class FakeStorage:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.reads = 0

    def put(self, name: str, data: bytes) -> None:
        self.objects[name] = data

    def read(self, object_name: str, *, generation: int | None = None) -> StoredObject:
        self.reads += 1
        if object_name not in self.objects:
            raise FileNotFoundError(object_name)
        data = self.objects[object_name]
        return StoredObject(
            data=data, bucket=BUCKET, name=object_name, generation=generation or 1,
            size=len(data), content_type="image/png", metadata={},
        )  # fmt: skip


class FakeExtractor:
    def __init__(self, outcomes: list[Any] | None = None) -> None:
        self.outcomes = outcomes or []
        self.calls: list[str | None] = []
        self.default = good_document()

    def extract(
        self, document: DocumentInput, *, document_id: str | None = None
    ) -> ExtractionResult:
        self.calls.append(document_id)
        outcome = self.outcomes.pop(0) if self.outcomes else self.default
        if isinstance(outcome, (ExtractionError, Exception)):
            raise outcome
        return ExtractionResult(
            document=outcome,
            metadata=ExtractionMetadata(
                model="gemini-test",
                model_version="gemini-test-001",
                prompt_version="p",
                location="global",
                latency_ms=12.0,
                attempts=1,
            ),
        )


class RecordingSink:
    def __init__(self) -> None:
        self.records: list[tuple[str, DocumentStatus]] = []
        self.fail_next = 0

    def record(
        self, record: DocumentRecord, *, status: DocumentStatus, extraction: Any, validation: Any
    ) -> None:
        if self.fail_next:
            self.fail_next -= 1
            raise RuntimeError("bigquery unavailable")
        self.records.append((record.document_id, status))

    @property
    def loaded(self) -> list[str]:
        """Documents published as approved transactions."""
        return [d for d, s in self.records if s is DocumentStatus.VALID]


class Env:
    def __init__(self) -> None:
        self.settings = Settings(
            _env_file=None, gcs_upload_bucket=BUCKET, max_upload_bytes=1_000_000,
            worker_lease_seconds=300, max_processing_attempts=3,
        )  # fmt: skip
        self.repo = InMemoryDocumentRepository()
        self.storage = FakeStorage()
        self.extractor = FakeExtractor()
        self.sink = RecordingSink()
        self.validator = DocumentValidator(
            ValidationConfig(supported_currencies=frozenset({"CAD", "USD"}))
        )
        self.processor = DocumentProcessor(
            self.settings, repository=self.repo, storage=self.storage,
            extractor_factory=lambda: self.extractor, validator=self.validator, sink=self.sink,
        )  # fmt: skip
        self._n = 0

    def upload(
        self, data: bytes | None = None, *, doc_id: str | None = None, user: str = USER
    ) -> tuple[str, StorageObjectEvent]:
        """Create the API-side record and the uploaded object; return (doc_id, finalize event)."""
        self._n += 1
        doc_id = doc_id or f"doc{self._n:03d}"
        data = png() if data is None else data
        name = f"uploads/{user}/{doc_id}/receipt.png"
        from datetime import UTC, datetime, timedelta

        self.repo.create(
            DocumentRecord(
                document_id=doc_id, user_id=user, status=DocumentStatus.AWAITING_UPLOAD,
                original_filename="receipt.png", bucket=BUCKET, object_name=name,
                content_type="image/png", size_bytes=len(data),
                created_at=datetime(2026, 11, 9, tzinfo=UTC) + timedelta(minutes=self._n),
            )
        )  # fmt: skip
        self.storage.put(name, data)
        return doc_id, self.event(name)

    def event(
        self, name: str, *, generation: int = 1, event_type: str = FINALIZED, bucket: str = BUCKET
    ) -> StorageObjectEvent:
        return StorageObjectEvent(
            id=f"evt-{name}-{generation}", type=event_type, source="//storage.googleapis.com/x",
            bucket=bucket, name=name, generation=generation, size=None, content_type="image/png",
        )  # fmt: skip


@pytest.fixture
def env() -> Env:
    return Env()
