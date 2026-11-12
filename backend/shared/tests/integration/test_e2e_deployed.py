"""End-to-end test against the DEPLOYED dev environment. Opt-in and billable (a few Gemini calls).

    make test-e2e

Nothing is faked: a real Firebase user signs in, the deployed API issues signed URLs, files go to
Cloud Storage, Eventarc triggers the deployed worker, Gemini extracts, the validator decides, and
results land in Firestore and BigQuery. The spec's ten steps, then deletion:

 1. Upload a receipt.                     6. Upload an invalid document.
 2. Eventarc triggers the worker.         7. Confirm it enters the review queue.
 3. Gemini extracts it.                   8. Correct the document.
 4. The response is validated.            9. Approve it.
 5. A valid record is loaded to BigQuery. 10. Verify the corrected record in BigQuery.
 11. Delete both documents through the API; verify the file, record and rows are gone.

The test user is created with a custom token (signed through IAM as the API's service account, so
no key or password exists) and deleted afterwards, together with anything the test left behind.
Needs: ADC with Token Creator on the API service account, E2E_API_URL and FIREBASE_WEB_API_KEY.
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

from receipt_shared.config import Settings

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("RUN_E2E") != "1",
        reason="set RUN_E2E=1 (runs against the deployed dev environment; billable)",
    ),
]

SAMPLES = Path(__file__).resolve().parents[4] / "evaluation" / "samples" / "out"
FINAL = {"VALID", "REVIEW_REQUIRED", "DUPLICATE", "FAILED"}
TOKEN_URL = "https://identitytoolkit.googleapis.com/v1/accounts:signInWithCustomToken"


class Deployed:
    def __init__(self, base_url: str, id_token: str, uid: str, settings: Settings) -> None:
        self.base = base_url.rstrip("/") + "/api/v1"
        self.headers = {"Authorization": f"Bearer {id_token}"}
        self.uid = uid
        self.settings = settings
        self.http = httpx.Client(timeout=60)

    def call(self, method: str, path: str, **kw: Any) -> httpx.Response:
        return self.http.request(method, self.base + path, headers=self.headers, **kw)

    def upload(self, filename: str) -> str:
        data = (SAMPLES / filename).read_bytes()
        resp = self.call("POST", "/documents/upload-url", json={
            "filename": filename, "content_type": "application/pdf", "size_bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
        })  # fmt: skip
        assert resp.status_code == 201, resp.text
        issued = resp.json()
        put = self.http.put(issued["upload_url"], content=data, headers=issued["headers"])
        assert put.status_code == 200, put.text
        return str(issued["document_id"])

    def wait(self, doc_id: str, timeout: float = 300) -> dict[str, Any]:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            body: dict[str, Any] = self.call("GET", f"/documents/{doc_id}/status").json()
            if body["status"] in FINAL:
                return body
            time.sleep(3)
        pytest.fail(f"{doc_id} was not processed within {timeout} s")

    def bq_rows(self, sql: str, doc_id: str) -> list[Any]:
        from google.cloud import bigquery

        from receipt_shared.analytics import qualified_dataset

        dataset = qualified_dataset(
            str(self.settings.gcp_project_id), self.settings.bigquery_dataset
        )
        client = bigquery.Client(project=self.settings.gcp_project_id)
        config = bigquery.QueryJobConfig(
            query_parameters=[bigquery.ScalarQueryParameter("d", "STRING", doc_id)]
        )
        return list(client.query(sql.format(ds=dataset), job_config=config).result())


@pytest.fixture(scope="module")
def deployed() -> Iterator[Deployed]:
    import firebase_admin
    from firebase_admin import auth

    settings = Settings()
    api_url = os.environ.get("E2E_API_URL")
    api_key = os.environ.get("FIREBASE_WEB_API_KEY")
    if not api_url or not api_key:
        pytest.fail("set E2E_API_URL and FIREBASE_WEB_API_KEY (make test-e2e does this)")
    project = str(settings.gcp_project_id)
    app = firebase_admin.initialize_app(
        options={
            "projectId": project,
            "serviceAccountId": settings.signing_service_account
            or f"receipt-api@{project}.iam.gserviceaccount.com",
        },
        name=f"e2e-{uuid.uuid4().hex[:8]}",
    )
    uid = f"e2e-{uuid.uuid4().hex[:16]}"
    custom = auth.create_custom_token(uid, app=app).decode()
    signed_in = httpx.post(
        TOKEN_URL,
        params={"key": api_key},
        json={"token": custom, "returnSecureToken": True},
        timeout=30,
    )
    assert signed_in.status_code == 200, signed_in.text
    env = Deployed(api_url, signed_in.json()["idToken"], uid, settings)
    try:
        yield env
    finally:
        _cleanup(env)
        auth.delete_user(uid, app=app)
        firebase_admin.delete_app(app)


def _cleanup(env: Deployed) -> None:
    """Remove anything a failed run left behind (a passing run deletes through the API)."""
    from google.cloud import bigquery, firestore, storage
    from google.cloud.firestore_v1.base_query import FieldFilter

    from receipt_shared.analytics import TABLES, qualified_dataset

    s = env.settings
    bucket = storage.Client(project=s.gcp_project_id).bucket(s.gcs_upload_bucket)
    for blob in bucket.list_blobs(prefix=f"uploads/{env.uid}/", versions=True):
        bucket.delete_blob(blob.name, generation=blob.generation)
    fs = firestore.Client(project=s.gcp_project_id, database=s.firestore_database)
    for snap in (
        fs.collection(s.firestore_documents_collection)
        .where(filter=FieldFilter("user_id", "==", env.uid))
        .stream()
    ):
        snap.reference.delete()
    bq = bigquery.Client(project=s.gcp_project_id)
    dataset = qualified_dataset(str(s.gcp_project_id), s.bigquery_dataset)
    for table in TABLES:
        bq.query(
            f"DELETE FROM `{dataset}.{table.name}` WHERE user_id = @u",  # noqa: S608
            job_config=bigquery.QueryJobConfig(
                query_parameters=[bigquery.ScalarQueryParameter("u", "STRING", env.uid)]
            ),
        ).result()


def test_upload_review_approve_delete(deployed: Deployed) -> None:
    d = deployed
    assert d.call("GET", "/health").json()["status"] == "ok"

    # 1-4: upload a valid receipt and an inconsistent one; the deployed pipeline processes both.
    good = d.upload("receipt_cafe.pdf")
    bad = d.upload("receipt_total_mismatch.pdf")
    assert d.wait(good)["status"] == "VALID"
    assert d.wait(bad)["status"] == "REVIEW_REQUIRED"
    detail = d.call("GET", f"/documents/{good}").json()
    assert detail["extraction"]["total_amount"] == "26.68"
    assert detail["model_version"]

    # 5: the valid record is in BigQuery as an AI-extracted transaction.
    tx = d.bq_rows(
        "SELECT total_amount, record_source, processing_status "
        "FROM `{ds}.extracted_transactions` WHERE document_id = @d",
        good,
    )
    assert [(str(r[0]), r[1], r[2]) for r in tx] == [("26.68", "AI", "VALID")]

    # 6-7: the inconsistent one is in the review queue and can't be approved as is.
    queue = d.call("GET", "/review").json()
    assert [item["document_id"] for item in queue["items"]] == [bad]
    assert d.call("POST", f"/review/{bad}/approve").status_code == 409

    # 8-9: correct the printed total (22.49 + 3.37 = 25.86), then approve.
    corrected = d.call("PATCH", f"/review/{bad}", json={"fields": {"total_amount": "25.86"}})
    assert corrected.status_code == 200, corrected.text
    assert corrected.json()["can_approve"] is True
    approved = d.call("POST", f"/review/{bad}/approve")
    assert approved.status_code == 200, approved.text
    assert approved.json()["document"]["status"] == "APPROVED"

    # 10: BigQuery holds the corrected value, marked as reviewed, with the audit trail.
    tx = d.bq_rows(
        "SELECT total_amount, record_source, processing_status "
        "FROM `{ds}.extracted_transactions` WHERE document_id = @d",
        bad,
    )
    assert [(str(r[0]), r[1], r[2]) for r in tx] == [("25.86", "REVIEWED", "APPROVED")]
    audit = d.bq_rows(
        "SELECT action, field_name, original_value, corrected_value "
        "FROM `{ds}.review_records` WHERE document_id = @d ORDER BY review_id",
        bad,
    )
    assert [(r[0], r[1], r[2], r[3]) for r in audit] == [
        ("APPROVE", None, None, None),
        ("CORRECTION", "total_amount", "28.86", "25.86"),
    ]

    # 11: deleting removes the file, the record and every BigQuery row.
    from google.cloud import storage

    bucket = storage.Client(project=d.settings.gcp_project_id).bucket(d.settings.gcs_upload_bucket)
    for doc_id in (good, bad):
        assert d.call("DELETE", f"/documents/{doc_id}").status_code == 204
        assert d.call("GET", f"/documents/{doc_id}").status_code == 404
        prefix = f"uploads/{d.uid}/{doc_id}/"
        assert list(bucket.list_blobs(prefix=prefix, versions=True)) == []
        for table in ("documents", "extracted_transactions", "line_items", "review_records",
                      "extraction_metrics"):  # fmt: skip
            sql = f"SELECT 1 FROM `{{ds}}.{table}` WHERE document_id = @d"  # noqa: S608
            assert d.bq_rows(sql, doc_id) == []
    assert d.call("GET", "/documents").json()["items"] == []
