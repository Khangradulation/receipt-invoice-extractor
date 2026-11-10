"""Live API: real Firestore, Cloud Storage, BigQuery and the deployed worker. Opt-in, billable.

    make test-api-live

Sign-in is the only part replaced: two fixed test users via a fake token verifier. Everything
created (objects, records, BigQuery rows) is deleted afterwards.
"""

from __future__ import annotations

import hashlib
import os
import time
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
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
        reason="set RUN_PIPELINE_INTEGRATION=1 (uses the deployed worker; billable)",
    ),
]

SAMPLES = Path(__file__).resolve().parents[4] / "evaluation" / "samples" / "out"
FINAL = {"VALID", "REVIEW_REQUIRED", "DUPLICATE", "FAILED"}


@pytest.fixture(scope="module")
def api() -> Iterator[dict[str, Any]]:
    from google.cloud import bigquery, firestore, storage
    from google.cloud.firestore_v1.base_query import FieldFilter

    from receipt_api.auth import CurrentUser, InvalidTokenError
    from receipt_api.main import create_app
    from receipt_shared.analytics import qualified_dataset

    settings = Settings()
    users = {"A": f"it-{uuid.uuid4().hex[:12]}", "B": f"it-{uuid.uuid4().hex[:12]}"}

    class Verifier:
        def verify(self, token: str) -> CurrentUser:
            if token not in users:
                raise InvalidTokenError("bad")
            return CurrentUser(uid=users[token])

    app = create_app(settings)
    app.state.token_verifier = Verifier()
    client = TestClient(app)
    yield {"client": client, "users": users, "settings": settings}

    bucket = storage.Client(project=settings.gcp_project_id).bucket(settings.gcs_upload_bucket)
    fs = firestore.Client(project=settings.gcp_project_id, database=settings.firestore_database)
    bq = bigquery.Client(project=settings.gcp_project_id)
    dataset = qualified_dataset(str(settings.gcp_project_id), settings.bigquery_dataset)
    for uid in users.values():
        for blob in bucket.list_blobs(prefix=f"uploads/{uid}/", versions=True):
            bucket.delete_blob(blob.name, generation=blob.generation)
        for snap in (
            fs.collection(settings.firestore_documents_collection)
            .where(filter=FieldFilter("user_id", "==", uid))
            .stream()
        ):
            snap.reference.delete()
        for table in (
            "documents",
            "extracted_transactions",
            "line_items",
            "extraction_metrics",
            "review_records",
        ):
            bq.query(
                f"DELETE FROM `{dataset}.{table}` WHERE user_id = @u",  # noqa: S608
                job_config=bigquery.QueryJobConfig(
                    query_parameters=[bigquery.ScalarQueryParameter("u", "STRING", uid)]
                ),
            ).result()


def call(api: dict[str, Any], method: str, path: str, user: str = "A", **kw: Any) -> httpx.Response:
    return api["client"].request(
        method, f"/api/v1{path}", headers={"Authorization": f"Bearer {user}"}, **kw
    )


def upload(api: dict[str, Any], filename: str) -> str:
    data = (SAMPLES / filename).read_bytes()
    issued = call(api, "POST", "/documents/upload-url", json={
        "filename": filename, "content_type": "application/pdf", "size_bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
    }).json()  # fmt: skip
    put = httpx.put(issued["upload_url"], content=data, headers=issued["headers"], timeout=60)
    assert put.status_code == 200
    return str(issued["document_id"])


def wait(api: dict[str, Any], doc_id: str) -> dict[str, Any]:
    deadline = time.monotonic() + 240
    while time.monotonic() < deadline:
        body: dict[str, Any] = call(api, "GET", f"/documents/{doc_id}/status").json()
        if body["status"] in FINAL:
            return body
        time.sleep(3)
    pytest.fail(f"{doc_id} not processed in time")


def test_full_api_flow(api: dict[str, Any]) -> None:
    good = upload(api, "receipt_cafe.pdf")
    bad = upload(api, "receipt_total_mismatch.pdf")
    assert wait(api, good)["status"] == "VALID"
    assert wait(api, bad)["status"] == "REVIEW_REQUIRED"

    # Listing (newest first) with paging — exercises the Firestore composite index.
    page1 = call(api, "GET", "/documents", params={"limit": 1}).json()
    page2 = call(
        api, "GET", "/documents", params={"limit": 1, "cursor": page1["next_cursor"]}
    ).json()
    assert [page1["items"][0]["document_id"], page2["items"][0]["document_id"]] == [bad, good]
    assert page2["next_cursor"] is None
    filtered = call(api, "GET", "/documents", params={"status": "VALID"}).json()
    assert [d["document_id"] for d in filtered["items"]] == [good]

    detail = call(api, "GET", f"/documents/{good}").json()
    assert detail["extraction"]["total_amount"] == "26.68"
    assert [h["status"] for h in detail["history"]][-1] == "VALID"
    assert call(api, "GET", f"/documents/{good}/extraction").json()["metadata"]["model_version"]
    file_url = call(api, "GET", f"/documents/{good}/file").json()["url"]
    assert httpx.get(file_url, timeout=60).content == (SAMPLES / "receipt_cafe.pdf").read_bytes()

    # Another user sees nothing.
    for path in (f"/documents/{good}", f"/documents/{good}/file", f"/review/{bad}"):
        assert call(api, "GET", path, user="B").status_code == 404
    assert call(api, "GET", "/documents", user="B").json()["items"] == []
    assert call(api, "POST", f"/review/{bad}/approve", user="B").status_code == 404

    # Review: correct the printed total (22.49 + 3.37 = 25.86), then approve.
    queue = call(api, "GET", "/review").json()
    assert [d["document_id"] for d in queue["items"]] == [bad]
    blocked = call(api, "POST", f"/review/{bad}/approve")
    assert blocked.status_code == 409
    corrected = call(
        api, "PATCH", f"/review/{bad}", json={"fields": {"total_amount": "25.86"}}
    ).json()
    assert corrected["can_approve"] is True, corrected["validation"]
    assert corrected["original"]["total_amount"] == "28.86"
    approved = call(api, "POST", f"/review/{bad}/approve")
    assert approved.status_code == 200, approved.text
    assert approved.json()["document"]["status"] == "APPROVED"
    api["approved"] = bad

    # BigQuery: corrected value + audit trail.
    from google.cloud import bigquery

    from receipt_shared.analytics import qualified_dataset

    s = api["settings"]
    dataset = qualified_dataset(str(s.gcp_project_id), s.bigquery_dataset)
    bq = bigquery.Client(project=s.gcp_project_id)
    params = bigquery.QueryJobConfig(
        query_parameters=[bigquery.ScalarQueryParameter("d", "STRING", bad)]
    )

    def rows(columns: str, table: str, order: str = "") -> list[Any]:
        sql = f"SELECT {columns} FROM `{dataset}.{table}` WHERE document_id = @d {order}"  # noqa: S608
        return list(bq.query(sql, job_config=params).result())

    tx = rows("total_amount, record_source, processing_status", "extracted_transactions")
    assert [(str(r["total_amount"]), r["record_source"], r["processing_status"]) for r in tx] == [
        ("25.86", "REVIEWED", "APPROVED")
    ]
    audit = rows(
        "action, field_name, original_value, corrected_value",
        "review_records",
        "ORDER BY review_id",
    )
    assert [
        (r["action"], r["field_name"], r["original_value"], r["corrected_value"]) for r in audit
    ] == [
        ("APPROVE", None, None, None),
        ("CORRECTION", "total_amount", "28.86", "25.86"),
    ]

    # Analytics from BigQuery for this user.
    today = datetime.now(UTC).date().isoformat()
    overview = call(
        api, "GET", "/analytics/overview", params={"start_date": "2026-01-01", "end_date": today}
    ).json()
    assert overview["total_spending"] == [
        {"currency": "CAD", "total_amount": "52.54", "total_tax": "6.85", "transaction_count": 2}
    ]
    assert overview["manual_review_rate"]["review_required"] == 1
    assert overview["manual_review_rate"]["review_rate"] == 0.5
    merchants = call(
        api, "GET", "/analytics/merchants", params={"start_date": "2026-01-01", "end_date": today}
    ).json()
    assert {r["merchant_name"] for r in merchants["rows"]} == {
        "Maple Leaf Cafe",
        "Harbour Books & Coffee",
    }
