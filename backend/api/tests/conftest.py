from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient

from receipt_api.auth import CurrentUser, InvalidTokenError
from receipt_api.main import create_app
from receipt_api.ratelimit import LIMITERS, TokenBucketLimiter
from receipt_api.review_service import ReviewService
from receipt_shared.analytics import AnalyticsRows
from receipt_shared.config import Settings
from receipt_shared.models.enums import DocumentStatus
from receipt_shared.models.extraction import (
    ExtractedDocument,
    ExtractionMetadata,
    ExtractionResult,
    LineItem,
)
from receipt_shared.repository import DocumentRecord, InMemoryDocumentRepository
from receipt_shared.storage.gcs import SignedUrl
from receipt_shared.validation import DocumentValidator, ValidationConfig

TOKENS = {"token-a": CurrentUser(uid="user_A"), "token-b": CurrentUser(uid="user_B")}
T0 = datetime(2026, 11, 9, 12, tzinfo=UTC)


class Verifier:
    def verify(self, token: str) -> CurrentUser:
        if token not in TOKENS:
            raise InvalidTokenError("bad")
        return TOKENS[token]


class FakeStorage:
    bucket_name = "docs-bucket"

    def upload_url(self, object_name: str, *, content_type: str, size_bytes: int) -> SignedUrl:
        return SignedUrl(url=f"https://x/{object_name}", method="PUT", expires_at=T0, headers={})

    def __init__(self) -> None:
        self.deleted: list[str] = []
        self.fail_delete = False

    def download_url(self, object_name: str, *, filename: str | None = None) -> SignedUrl:
        return SignedUrl(url=f"https://x/{object_name}?get", method="GET", expires_at=T0)

    def delete_all_versions(self, object_name: str) -> int:
        if self.fail_delete:
            raise RuntimeError("storage down")
        self.deleted.append(object_name)
        return 2


class RecordingWriter:
    def __init__(self) -> None:
        self.rows: list[AnalyticsRows] = []
        self.deleted: list[str] = []
        self.fail = False

    def write(self, rows: AnalyticsRows) -> None:
        if self.fail:
            from receipt_shared.analytics import AnalyticsWriteError

            raise AnalyticsWriteError("down", retryable=True)
        self.rows.append(rows)

    def delete(self, document_id: str) -> None:
        if self.fail:
            from receipt_shared.analytics import AnalyticsWriteError

            raise AnalyticsWriteError("down", retryable=True)
        self.deleted.append(document_id)


class FakeQueries:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def run(self, name: str, **kwargs: Any) -> list[dict[str, Any]]:
        self.calls.append({"name": name, **kwargs})
        if name == "processing_success_rate":
            return [{"processed_documents": 3, "success_rate": 1.0}]
        if name == "manual_review_rate":
            return [{"review_rate": 0.5}]
        return [{"query": name, "user_id": kwargs.get("user_id")}]


def document(**overrides: Any) -> ExtractedDocument:
    base: dict[str, Any] = {
        "document_type": "receipt",
        "document_number": "R-1",
        "document_date": date(2026, 3, 14),
        "currency": "CAD",
        "merchant_name": "Maple Leaf Cafe",
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


class Env:
    def __init__(self) -> None:
        self.settings = Settings(_env_file=None, gcp_project_id="p", max_upload_bytes=1000)
        self.app = create_app(self.settings)
        self.repo = InMemoryDocumentRepository()
        self.writer = RecordingWriter()
        self.queries = FakeQueries()
        self.app.state.token_verifier = Verifier()
        self.storage = FakeStorage()
        self.app.state.storage = self.storage
        self.app.state.analytics_writer = self.writer
        self.app.state.repository = self.repo
        self.app.state.analytics = self.queries
        self.app.state.review_service = ReviewService(
            repository=self.repo,
            validator=DocumentValidator(
                ValidationConfig(supported_currencies=frozenset({"CAD", "USD"}))
            ),
            writer=self.writer,
        )
        self.client = TestClient(self.app)
        self._n = 0

    def add(
        self,
        user: str = "user_A",
        status: DocumentStatus = DocumentStatus.VALID,
        *,
        doc: ExtractedDocument | None = None,
        extracted: bool = True,
    ) -> str:
        from receipt_shared.validation import DocumentValidator as V

        self._n += 1
        doc_id = f"doc{self._n:03d}"
        doc = doc or document()
        record: dict[str, Any] = {
            "document_id": doc_id,
            "user_id": user,
            "status": status,
            "original_filename": f"r{self._n}.pdf",
            "bucket": "docs-bucket",
            "object_name": f"uploads/{user}/{doc_id}/r.pdf",
            "content_type": "application/pdf",
            "size_bytes": 100,
            "file_sha256": f"{self._n:064d}",
            "object_generation": 1,
            "created_at": T0 + timedelta(minutes=self._n),
            "updated_at": T0,
            "history": [{"status": "UPLOADED", "at": T0}],
        }
        if extracted and status is not DocumentStatus.AWAITING_UPLOAD:
            result = ExtractionResult(
                document=doc,
                metadata=ExtractionMetadata(
                    model="m",
                    model_version="m-001",
                    prompt_version="p",
                    location="global",
                    latency_ms=1.0,
                    attempts=1,
                ),
            )
            record["extraction"] = result.model_dump(mode="json")
            validation = V(
                ValidationConfig(supported_currencies=frozenset({"CAD", "USD"}))
            ).validate(
                doc, document_id=doc_id, user_id=user, file_sha256="x", today=date(2026, 11, 9)
            )
            record["validation"] = validation.model_dump(mode="json")
        self.repo.create(DocumentRecord(**record))
        return doc_id

    def get(self, path: str, token: str | None = "token-a", **kw: Any) -> Any:
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        return self.client.get(f"/api/v1{path}", headers=headers, **kw)

    def send(self, method: str, path: str, body: Any = None, token: str = "token-a") -> Any:
        return self.client.request(
            method, f"/api/v1{path}", json=body, headers={"Authorization": f"Bearer {token}"}
        )


@pytest.fixture
def env() -> Env:
    return Env()


@pytest.fixture(autouse=True)
def _fresh_rate_limits() -> None:
    for name, limiter in list(LIMITERS.items()):
        LIMITERS[name] = TokenBucketLimiter(int(limiter.capacity))
    from receipt_api.routers import analytics

    analytics.CACHE._items.clear()
