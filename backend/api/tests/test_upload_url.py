from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient

from receipt_api.auth import CurrentUser, FirebaseTokenVerifier, InvalidTokenError
from receipt_api.main import create_app
from receipt_shared.config import Settings
from receipt_shared.models.enums import DocumentStatus
from receipt_shared.repository import InMemoryDocumentRepository
from receipt_shared.storage.gcs import SignedUrl

GOOD_TOKEN = "good-token"


class FakeVerifier:
    def verify(self, token: str) -> CurrentUser:
        if token != GOOD_TOKEN:
            raise InvalidTokenError("bad")
        return CurrentUser(uid="user_A", email="a@example.test")


class FakeStorage:
    bucket_name = "docs-bucket"

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def upload_url(self, object_name: str, *, content_type: str, size_bytes: int) -> SignedUrl:
        self.calls.append(
            {"object_name": object_name, "content_type": content_type, "size": size_bytes}
        )
        return SignedUrl(
            url=f"https://storage.googleapis.com/docs-bucket/{object_name}?sig=1",
            method="PUT",
            expires_at=datetime(2026, 11, 9, 12, 15, tzinfo=UTC),
            headers={
                "Content-Type": content_type,
                "x-goog-content-length-range": f"{size_bytes},{size_bytes}",
            },
        )


@pytest.fixture
def env() -> tuple[TestClient, FakeStorage, InMemoryDocumentRepository]:
    app = create_app(Settings(_env_file=None, gcp_project_id="p", max_upload_bytes=1000))
    storage, repo = FakeStorage(), InMemoryDocumentRepository()
    app.state.token_verifier = FakeVerifier()
    app.state.storage = storage
    app.state.repository = repo
    return TestClient(app), storage, repo


def post(client: TestClient, body: dict[str, Any], token: str | None = GOOD_TOKEN) -> Any:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return client.post("/api/v1/documents/upload-url", json=body, headers=headers)


PDF_BODY = {"filename": "Receipt 1.pdf", "content_type": "application/pdf", "size_bytes": 500}


def test_requires_sign_in(env: Any) -> None:
    client, storage, _ = env
    resp = post(client, PDF_BODY, token=None)
    assert resp.status_code == 401
    assert resp.headers["WWW-Authenticate"] == "Bearer"
    assert resp.json()["error"]["code"] == "unauthorized"
    assert storage.calls == []


def test_rejects_invalid_token(env: Any) -> None:
    client, storage, _ = env
    resp = post(client, PDF_BODY, token="forged")
    assert resp.status_code == 401
    assert storage.calls == []


def test_issues_url_and_creates_record(env: Any) -> None:
    client, storage, repo = env
    resp = post(client, PDF_BODY | {"sha256": "AB" * 32})
    assert resp.status_code == 201
    body = resp.json()
    doc_id = body["document_id"]
    assert len(doc_id) == 32
    assert body["status"] == "AWAITING_UPLOAD"
    assert body["method"] == "PUT"
    assert body["headers"]["x-goog-content-length-range"] == "500,500"
    assert storage.calls == [
        {
            "object_name": f"uploads/user_A/{doc_id}/Receipt_1.pdf",
            "content_type": "application/pdf",
            "size": 500,
        }
    ]
    record = repo.get(doc_id)
    assert record is not None
    assert record.user_id == "user_A"
    assert record.status is DocumentStatus.AWAITING_UPLOAD
    assert record.original_filename == "Receipt 1.pdf"
    assert record.client_sha256 == "ab" * 32
    assert record.bucket == "docs-bucket"


def test_user_id_in_body_is_ignored(env: Any) -> None:
    client, storage, repo = env
    resp = post(client, PDF_BODY | {"user_id": "victim"})
    assert resp.status_code == 201
    assert repo.get(resp.json()["document_id"]).user_id == "user_A"
    assert "/victim/" not in storage.calls[0]["object_name"]


def test_each_request_gets_a_new_document_id(env: Any) -> None:
    client, _, _ = env
    ids = {post(client, PDF_BODY).json()["document_id"] for _ in range(3)}
    assert len(ids) == 3


@pytest.mark.parametrize(
    ("filename", "content_type"),
    [
        ("a.png", "image/png"),
        ("a.JPG", "image/jpeg"),
        ("a.jpeg", "image/jpg"),
        ("a.pdf", "application/pdf"),
    ],
)
def test_supported_types(env: Any, filename: str, content_type: str) -> None:
    client, _, _ = env
    resp = post(client, {"filename": filename, "content_type": content_type, "size_bytes": 10})
    assert resp.status_code == 201


@pytest.mark.parametrize(
    ("filename", "content_type"),
    [
        ("a.gif", "image/gif"),
        ("a.exe", "application/pdf"),
        ("a.pdf", "text/html"),
        ("noext", "application/pdf"),
    ],
)
def test_unsupported_types_rejected(env: Any, filename: str, content_type: str) -> None:
    client, storage, _ = env
    resp = post(client, {"filename": filename, "content_type": content_type, "size_bytes": 10})
    assert resp.status_code == 415
    assert resp.json()["error"]["code"] == "unsupported_file_type"
    assert storage.calls == []


def test_extension_type_mismatch_rejected(env: Any) -> None:
    client, _, _ = env
    resp = post(client, {"filename": "a.png", "content_type": "application/pdf", "size_bytes": 10})
    assert resp.status_code == 415
    assert "does not match" in resp.json()["error"]["message"]


def test_too_large_rejected(env: Any) -> None:
    client, storage, _ = env
    resp = post(client, PDF_BODY | {"size_bytes": 1001})
    assert resp.status_code == 413
    assert resp.json()["error"]["code"] == "file_too_large"
    assert storage.calls == []


@pytest.mark.parametrize("size", [0, -5])
def test_non_positive_size_rejected(env: Any, size: int) -> None:
    client, _, _ = env
    assert post(client, PDF_BODY | {"size_bytes": size}).status_code == 422


def test_bad_checksum_format_rejected(env: Any) -> None:
    client, _, _ = env
    resp = post(client, PDF_BODY | {"sha256": "not-a-hash"})
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "validation_error"


def test_storage_not_configured_returns_503() -> None:
    app = create_app(Settings(_env_file=None, gcp_project_id="p", gcs_upload_bucket=None))
    app.state.token_verifier = FakeVerifier()
    app.state.repository = InMemoryDocumentRepository()
    resp = post(TestClient(app), PDF_BODY)
    assert resp.status_code == 503


# --- Firebase verifier -------------------------------------------------------------------------
def test_firebase_verifier_maps_claims(monkeypatch: pytest.MonkeyPatch) -> None:
    from firebase_admin import auth

    captured: dict[str, Any] = {}

    def fake_verify(
        token: str, app: Any = None, check_revoked: bool = False, clock_skew_seconds: int = 0
    ) -> dict[str, Any]:
        captured.update(token=token, skew=clock_skew_seconds)
        return {"uid": "abc", "sub": "abc", "email": "x@example.test"}

    monkeypatch.setattr(auth, "verify_id_token", fake_verify)
    verifier = FirebaseTokenVerifier(Settings(_env_file=None, firebase_project_id="p"))
    monkeypatch.setattr(verifier, "_get_app", lambda: object())
    assert verifier.verify("t") == CurrentUser(uid="abc", email="x@example.test")
    assert captured == {"token": "t", "skew": 10}


@pytest.mark.parametrize(
    "error", ["ExpiredIdTokenError", "RevokedIdTokenError", "InvalidIdTokenError"]
)
def test_firebase_verifier_rejects_bad_tokens(monkeypatch: pytest.MonkeyPatch, error: str) -> None:
    from firebase_admin import auth

    exc_cls = getattr(auth, error)

    def fake_verify(*args: Any, **kwargs: Any) -> dict[str, Any]:
        try:
            raise exc_cls("bad", cause=None)
        except TypeError:  # constructors differ between firebase-admin error classes
            raise exc_cls("bad") from None

    monkeypatch.setattr(auth, "verify_id_token", fake_verify)
    verifier = FirebaseTokenVerifier(Settings(_env_file=None, firebase_project_id="p"))
    monkeypatch.setattr(verifier, "_get_app", lambda: object())
    with pytest.raises(InvalidTokenError):
        verifier.verify("t")


def test_firebase_verifier_requires_project() -> None:
    with pytest.raises(RuntimeError, match="FIREBASE_PROJECT_ID"):
        FirebaseTokenVerifier(
            Settings(_env_file=None, firebase_project_id=None, gcp_project_id=None)
        )
