"""Live Cloud Storage + Firestore round trip through the real API endpoint. Opt-in.

    make test-storage-live

Needs GCP_PROJECT_ID, GCS_UPLOAD_BUCKET and SIGNING_SERVICE_ACCOUNT, plus ADC for a user with
Token Creator on the signing service account. Sign-in is the only thing replaced (a fixed test
user via a fake token verifier). Everything the test creates is deleted afterwards.
"""

from __future__ import annotations

import hashlib
import os
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from receipt_shared.config import Settings

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("RUN_GCP_INTEGRATION") != "1",
        reason="set RUN_GCP_INTEGRATION=1 to use real Cloud Storage and Firestore",
    ),
]

SAMPLE = Path(__file__).resolve().parents[4] / "evaluation" / "samples" / "out" / "receipt_cafe.pdf"


@pytest.fixture(scope="module")
def live() -> Iterator[dict[str, Any]]:
    from google.cloud import firestore, storage

    from receipt_api.auth import CurrentUser
    from receipt_api.main import create_app
    from receipt_shared.repository import FirestoreDocumentRepository
    from receipt_shared.storage import DocumentStorage

    settings = Settings()
    if not (
        settings.gcp_project_id and settings.gcs_upload_bucket and settings.signing_service_account
    ):
        pytest.skip("GCP_PROJECT_ID / GCS_UPLOAD_BUCKET / SIGNING_SERVICE_ACCOUNT not set")
    if not SAMPLE.exists():
        pytest.skip("run evaluation/samples/generate_samples.py first")

    user_id = f"it-{uuid.uuid4().hex[:12]}"

    class TestUserVerifier:
        def verify(self, token: str) -> CurrentUser:
            return CurrentUser(uid=user_id)

    app = create_app(settings)
    app.state.token_verifier = TestUserVerifier()
    app.state.storage = DocumentStorage(settings)
    app.state.repository = FirestoreDocumentRepository.from_settings(settings)

    fs = firestore.Client(project=settings.gcp_project_id, database=settings.firestore_database)
    gcs = storage.Client(project=settings.gcp_project_id)
    created: list[str] = []
    yield {
        "client": TestClient(app),
        "settings": settings,
        "user_id": user_id,
        "storage": app.state.storage,
        "repo": app.state.repository,
        "created": created,
    }

    bucket = gcs.bucket(settings.gcs_upload_bucket)
    for blob in bucket.list_blobs(prefix=f"uploads/{user_id}/", versions=True):
        bucket.delete_blob(blob.name, generation=blob.generation)
    for doc_id in created:
        fs.collection(settings.firestore_documents_collection).document(doc_id).delete()


def _request_url(live: dict[str, Any], data: bytes, **overrides: Any) -> dict[str, Any]:
    body = {
        "filename": "receipt_cafe.pdf",
        "content_type": "application/pdf",
        "size_bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
    } | overrides
    resp = live["client"].post(
        "/api/v1/documents/upload-url", json=body, headers={"Authorization": "Bearer test"}
    )
    assert resp.status_code == 201, resp.text
    payload: dict[str, Any] = resp.json()
    live["created"].append(payload["document_id"])
    return payload


def test_full_upload_round_trip(live: dict[str, Any]) -> None:
    from receipt_shared.storage.verify import verify_upload

    data = SAMPLE.read_bytes()
    issued = _request_url(live, data)

    record = live["repo"].get(issued["document_id"])
    assert record is not None
    assert record.user_id == live["user_id"]
    assert record.status.value == "AWAITING_UPLOAD"
    assert (
        record.object_name == f"uploads/{live['user_id']}/{issued['document_id']}/receipt_cafe.pdf"
    )

    put = httpx.put(issued["upload_url"], content=data, headers=issued["headers"], timeout=60)
    assert put.status_code == 200, put.text

    obj = live["storage"].read(record.object_name)
    assert obj.data == data
    document = verify_upload(
        obj,
        live["settings"],
        expected_content_type=record.content_type,
        expected_size=record.size_bytes,
        expected_sha256=record.client_sha256,
        filename=record.original_filename,
    )
    assert document.page_count == 1

    # Signed download URL works...
    download = live["storage"].download_url(record.object_name, filename="receipt_cafe.pdf")
    got = httpx.get(download.url, timeout=60)
    assert got.status_code == 200
    assert got.content == data

    # ...but the object is not publicly readable.
    public = httpx.get(
        f"https://storage.googleapis.com/{live['settings'].gcs_upload_bucket}/{record.object_name}",
        timeout=60,
    )
    assert public.status_code in (401, 403)


def test_upload_url_rejects_wrong_content_type(live: dict[str, Any]) -> None:
    data = SAMPLE.read_bytes()
    issued = _request_url(live, data)
    headers = issued["headers"] | {"Content-Type": "text/html"}
    put = httpx.put(issued["upload_url"], content=data, headers=headers, timeout=60)
    assert put.status_code == 403  # signature covers the content type


def test_upload_url_rejects_wrong_size(live: dict[str, Any]) -> None:
    data = SAMPLE.read_bytes()
    issued = _request_url(live, data)
    put = httpx.put(
        issued["upload_url"], content=data + b"extra", headers=issued["headers"], timeout=60
    )
    assert put.status_code == 400  # x-goog-content-length-range enforces the declared size
    assert not live["storage"].exists(live["repo"].get(issued["document_id"]).object_name)


def test_upload_url_cannot_be_used_for_another_path(live: dict[str, Any]) -> None:
    data = SAMPLE.read_bytes()
    issued = _request_url(live, data)
    other = issued["upload_url"].replace(issued["document_id"], uuid.uuid4().hex)
    put = httpx.put(other, content=data, headers=issued["headers"], timeout=60)
    assert put.status_code == 403
