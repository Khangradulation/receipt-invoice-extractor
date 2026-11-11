from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from receipt_shared.models.enums import DocumentStatus

from .conftest import Env


def test_delete_removes_file_rows_and_record(env: Env) -> None:
    doc_id = env.add(status=DocumentStatus.APPROVED)
    resp = env.send("DELETE", f"/documents/{doc_id}")
    assert resp.status_code == 204
    assert resp.content == b""
    assert env.storage.deleted == [f"uploads/user_A/{doc_id}/r.pdf"]
    assert env.writer.deleted == [doc_id]
    assert env.repo.get(doc_id) is None
    assert env.get(f"/documents/{doc_id}").status_code == 404


def test_cannot_delete_other_users_documents(env: Env) -> None:
    doc_id = env.add(user="user_B")
    resp = env.send("DELETE", f"/documents/{doc_id}")
    assert resp.status_code == 404  # same answer as a missing document
    assert env.repo.get(doc_id) is not None
    assert env.storage.deleted == []
    assert env.writer.deleted == []


def test_delete_requires_sign_in(env: Env) -> None:
    doc_id = env.add()
    resp = env.client.delete(f"/api/v1/documents/{doc_id}")
    assert resp.status_code == 401
    assert env.repo.get(doc_id) is not None


def test_delete_unknown_or_malformed_id_is_404(env: Env) -> None:
    assert env.send("DELETE", "/documents/nope").status_code == 404
    assert env.send("DELETE", "/documents/..%2F..%2Fetc").status_code == 404


def test_refuses_while_upload_link_is_still_valid(env: Env) -> None:
    doc_id = env.add(status=DocumentStatus.AWAITING_UPLOAD)
    future = datetime.now(UTC) + timedelta(minutes=10)
    env.repo.update(doc_id, {"upload_url_expires_at": future})
    resp = env.send("DELETE", f"/documents/{doc_id}")
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "conflict"
    assert env.repo.get(doc_id) is not None

    env.repo.update(doc_id, {"upload_url_expires_at": datetime.now(UTC) - timedelta(seconds=1)})
    assert env.send("DELETE", f"/documents/{doc_id}").status_code == 204


def test_refuses_while_worker_holds_a_live_lease(env: Env) -> None:
    doc_id = env.add(status=DocumentStatus.PROCESSING, extracted=False)
    env.repo.update(doc_id, {"lease_expires_at": datetime.now(UTC) + timedelta(minutes=5)})
    assert env.send("DELETE", f"/documents/{doc_id}").status_code == 409

    # A stale lease (crashed worker) no longer blocks deletion.
    env.repo.update(doc_id, {"lease_expires_at": datetime.now(UTC) - timedelta(minutes=1)})
    assert env.send("DELETE", f"/documents/{doc_id}").status_code == 204


def test_failed_step_keeps_the_record_so_the_delete_can_be_retried(env: Env) -> None:
    doc_id = env.add(status=DocumentStatus.VALID)
    env.writer.fail = True
    resp = env.send("DELETE", f"/documents/{doc_id}")
    assert resp.status_code == 503
    assert env.repo.get(doc_id) is not None  # still visible, so the user can retry

    env.writer.fail = False
    assert env.send("DELETE", f"/documents/{doc_id}").status_code == 204
    assert env.repo.get(doc_id) is None


def test_storage_failure_keeps_everything(env: Env) -> None:
    doc_id = env.add()
    env.storage.fail_delete = True
    client = TestClient(env.app, raise_server_exceptions=False)
    resp = client.delete(f"/api/v1/documents/{doc_id}", headers={"Authorization": "Bearer token-a"})
    assert resp.status_code == 500
    assert resp.json()["error"]["code"] == "internal_error"
    assert env.writer.deleted == []
    assert env.repo.get(doc_id) is not None
