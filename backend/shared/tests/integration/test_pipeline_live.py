"""Live end-to-end pipeline: upload -> Eventarc -> Cloud Run worker -> Gemini -> Firestore.

Opt-in and billable (a few Gemini calls):

    make test-pipeline-live

Requires the deployed worker and Eventarc trigger (ops/gcp/deploy-worker.sh). Sign-in is the
only part replaced (fixed test user). Uploaded objects and records are deleted afterwards.
"""

from __future__ import annotations

import hashlib
import os
import time
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
        os.environ.get("RUN_PIPELINE_INTEGRATION") != "1",
        reason="set RUN_PIPELINE_INTEGRATION=1 to run the deployed pipeline (billable)",
    ),
]

SAMPLES = Path(__file__).resolve().parents[4] / "evaluation" / "samples" / "out"
FINAL = {"VALID", "REVIEW_REQUIRED", "DUPLICATE", "FAILED"}


@pytest.fixture(scope="module")
def live() -> Iterator[dict[str, Any]]:
    from google.cloud import firestore, storage

    from receipt_api.auth import CurrentUser
    from receipt_api.main import create_app
    from receipt_shared.repository import FirestoreDocumentRepository
    from receipt_shared.storage import DocumentStorage

    settings = Settings()
    if not (settings.gcs_upload_bucket and settings.signing_service_account):
        pytest.skip("GCS_UPLOAD_BUCKET / SIGNING_SERVICE_ACCOUNT not set")
    user_id = f"it-{uuid.uuid4().hex[:12]}"

    class TestUserVerifier:
        def verify(self, token: str) -> CurrentUser:
            return CurrentUser(uid=user_id)

    app = create_app(settings)
    app.state.token_verifier = TestUserVerifier()
    app.state.storage = DocumentStorage(settings)
    app.state.repository = FirestoreDocumentRepository.from_settings(settings)
    created: list[str] = []
    yield {"client": TestClient(app), "repo": app.state.repository, "created": created}

    bucket = storage.Client(project=settings.gcp_project_id).bucket(settings.gcs_upload_bucket)
    for blob in bucket.list_blobs(prefix=f"uploads/{user_id}/", versions=True):
        bucket.delete_blob(blob.name, generation=blob.generation)
    fs = firestore.Client(project=settings.gcp_project_id, database=settings.firestore_database)
    for doc_id in created:
        fs.collection(settings.firestore_documents_collection).document(doc_id).delete()


def upload(live: dict[str, Any], filename: str) -> str:
    path = SAMPLES / filename
    if not path.exists():
        pytest.skip("run evaluation/samples/generate_samples.py first")
    data = path.read_bytes()
    resp = live["client"].post(
        "/api/v1/documents/upload-url",
        json={
            "filename": filename,
            "content_type": "application/pdf",
            "size_bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
        },
        headers={"Authorization": "Bearer test"},
    )
    assert resp.status_code == 201, resp.text
    issued = resp.json()
    live["created"].append(issued["document_id"])
    put = httpx.put(issued["upload_url"], content=data, headers=issued["headers"], timeout=60)
    assert put.status_code == 200, put.text
    return str(issued["document_id"])


def wait_final(live: dict[str, Any], doc_id: str, timeout: float = 180) -> Any:
    deadline = time.monotonic() + timeout
    record = None
    while time.monotonic() < deadline:
        record = live["repo"].get(doc_id)
        if record is not None and record.status.value in FINAL:
            return record
        time.sleep(3)
    pytest.fail(f"{doc_id} not processed in {timeout}s (last status: {record and record.status})")


def test_valid_receipt_is_processed_automatically(live: dict[str, Any]) -> None:
    doc_id = upload(live, "receipt_cafe.pdf")
    record = wait_final(live, doc_id)
    assert record.status.value == "VALID", record.validation
    assert [h["status"] for h in record.history] == [
        "UPLOADED", "PROCESSING", "EXTRACTED", "VALIDATING", "VALID",
    ]  # fmt: skip
    assert record.processing_attempts == 1
    assert record.object_generation
    assert record.model_version
    assert record.extraction["document"]["total_amount"] == "26.68"
    assert record.extraction["document"]["merchant_name"] == "Maple Leaf Cafe"
    assert record.processing_duration_ms > 0
    live["valid_doc"] = doc_id


def test_inconsistent_receipt_goes_to_review(live: dict[str, Any]) -> None:
    doc_id = upload(live, "receipt_total_mismatch.pdf")
    record = wait_final(live, doc_id)
    assert record.status.value == "REVIEW_REQUIRED"
    codes = [e["code"] for e in record.validation["validation_errors"]]
    assert "TOTAL_MISMATCH" in codes
    assert "total_amount" in record.validation["failed_fields"]


def test_same_file_again_is_duplicate(live: dict[str, Any]) -> None:
    first = live.get("valid_doc")
    if first is None:
        pytest.skip("depends on test_valid_receipt_is_processed_automatically")
    doc_id = upload(live, "receipt_cafe.pdf")
    record = wait_final(live, doc_id)
    assert record.status.value == "DUPLICATE"
    assert record.validation["duplicate_of"] == [first]
