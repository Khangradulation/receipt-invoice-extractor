import pytest

from receipt_shared.models.enums import DocumentStatus

from .conftest import Env


@pytest.mark.parametrize(
    "path",
    [
        "/documents",
        "/documents/doc001",
        "/documents/doc001/status",
        "/documents/doc001/extraction",
        "/documents/doc001/file",
        "/review",
        "/review/doc001",
        "/analytics/overview",
    ],
)
def test_every_endpoint_requires_sign_in(env: Env, path: str) -> None:
    env.add()
    assert env.get(path, token=None).status_code == 401
    assert env.get(path, token="forged").status_code == 401


def test_list_shows_only_own_documents_newest_first(env: Env) -> None:
    a1 = env.add("user_A")
    env.add("user_B")
    a2 = env.add("user_A", DocumentStatus.REVIEW_REQUIRED)
    body = env.get("/documents").json()
    assert [d["document_id"] for d in body["items"]] == [a2, a1]
    first = body["items"][1]
    assert first["merchant_name"] == "Maple Leaf Cafe"
    assert first["total_amount"] == "26.68"
    assert body["next_cursor"] is None


def test_pagination_with_cursor(env: Env) -> None:
    ids = [env.add() for _ in range(5)]
    page1 = env.get("/documents", params={"limit": 2}).json()
    page2 = env.get("/documents", params={"limit": 2, "cursor": page1["next_cursor"]}).json()
    page3 = env.get("/documents", params={"limit": 2, "cursor": page2["next_cursor"]}).json()
    seen = [d["document_id"] for p in (page1, page2, page3) for d in p["items"]]
    assert seen == list(reversed(ids))
    assert page3["next_cursor"] is None


def test_status_filter(env: Env) -> None:
    env.add(status=DocumentStatus.VALID)
    r = env.add(status=DocumentStatus.REVIEW_REQUIRED)
    body = env.get("/documents", params={"status": "REVIEW_REQUIRED"}).json()
    assert [d["document_id"] for d in body["items"]] == [r]


def test_invalid_cursor_and_limit(env: Env) -> None:
    assert env.get("/documents", params={"cursor": "%%%not-a-cursor"}).status_code == 400
    assert env.get("/documents", params={"limit": 0}).status_code == 422
    assert env.get("/documents", params={"limit": 101}).status_code == 422


def test_document_detail(env: Env) -> None:
    doc_id = env.add()
    body = env.get(f"/documents/{doc_id}").json()
    assert body["document_id"] == doc_id
    assert body["extraction"]["merchant_name"] == "Maple Leaf Cafe"
    assert body["corrected"] is None
    assert body["validation"]["validation_status"] == "VALID"
    assert body["history"][0]["status"] == "UPLOADED"


@pytest.mark.parametrize("suffix", ["", "/status", "/extraction", "/file"])
def test_other_users_documents_are_not_found(env: Env, suffix: str) -> None:
    other = env.add("user_B")
    resp = env.get(f"/documents/{other}{suffix}")
    assert resp.status_code == 404
    assert resp.json()["error"]["message"] == "Document not found."  # same as a missing document
    assert env.get(f"/documents/{other}{suffix}", token="token-b").status_code == 200


@pytest.mark.parametrize("doc_id", ["nope", "a.b", "..", "x" * 200])
def test_unknown_or_malformed_ids_are_not_found(env: Env, doc_id: str) -> None:
    assert env.get(f"/documents/{doc_id}").status_code == 404


def test_status_endpoint(env: Env) -> None:
    doc_id = env.add(status=DocumentStatus.PROCESSING, extracted=False)
    body = env.get(f"/documents/{doc_id}/status").json()
    assert body["status"] == "PROCESSING"
    assert body["error"] is None


def test_failed_document_exposes_error(env: Env) -> None:
    doc_id = env.add(status=DocumentStatus.FAILED, extracted=False)
    env.repo.update(
        doc_id, {"last_error": {"code": "integrity_check_failed", "message": "Size mismatch."}}
    )
    body = env.get(f"/documents/{doc_id}/status").json()
    assert body["error"] == {"code": "integrity_check_failed", "message": "Size mismatch."}


def test_extraction_endpoint(env: Env) -> None:
    doc_id = env.add()
    body = env.get(f"/documents/{doc_id}/extraction").json()
    assert body["document"]["total_amount"] == "26.68"
    assert body["metadata"]["model_version"] == "m-001"
    not_yet = env.add(status=DocumentStatus.PROCESSING, extracted=False)
    assert env.get(f"/documents/{not_yet}/extraction").status_code == 404


def test_file_url(env: Env) -> None:
    doc_id = env.add()
    body = env.get(f"/documents/{doc_id}/file").json()
    assert body["url"].endswith("?get")
    assert body["content_type"] == "application/pdf"
    waiting = env.add(status=DocumentStatus.AWAITING_UPLOAD, extracted=False)
    assert env.get(f"/documents/{waiting}/file").status_code == 404


def test_openapi_lists_all_endpoints(env: Env) -> None:
    paths = env.client.get("/api/v1/openapi.json").json()["paths"]
    for p in [
        "/api/v1/documents/upload-url",
        "/api/v1/documents",
        "/api/v1/documents/{document_id}",
        "/api/v1/documents/{document_id}/status",
        "/api/v1/documents/{document_id}/extraction",
        "/api/v1/review",
        "/api/v1/review/{document_id}",
        "/api/v1/review/{document_id}/approve",
        "/api/v1/review/{document_id}/reject",
        "/api/v1/analytics/overview",
        "/api/v1/analytics/monthly-spending",
        "/api/v1/analytics/categories",
        "/api/v1/analytics/merchants",
        "/api/v1/health",
    ]:
        assert p in paths, p
    assert "patch" in paths["/api/v1/review/{document_id}"]
