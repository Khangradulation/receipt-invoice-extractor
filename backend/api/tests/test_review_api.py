from decimal import Decimal

import pytest

from receipt_shared.models.enums import DocumentStatus

from .conftest import Env, document


def bad_total(env: Env, user: str = "user_A") -> str:
    return env.add(
        user, DocumentStatus.REVIEW_REQUIRED, doc=document(total_amount=Decimal("99.00"))
    )


def test_queue_lists_only_own_review_items(env: Env) -> None:
    mine = bad_total(env)
    bad_total(env, "user_B")
    env.add("user_A", DocumentStatus.VALID)
    items = env.get("/review").json()["items"]
    assert [i["document_id"] for i in items] == [mine]


def test_review_detail(env: Env) -> None:
    doc_id = bad_total(env)
    body = env.get(f"/review/{doc_id}").json()
    assert body["can_approve"] is False
    assert "total_amount" in body["failed_fields"]
    assert body["original"]["total_amount"] == "99.00"
    assert body["current"]["total_amount"] == "99.00"
    assert body["corrections"] == []


def test_correction_revalidates_and_keeps_original(env: Env) -> None:
    doc_id = bad_total(env)
    resp = env.send("PATCH", f"/review/{doc_id}", {"fields": {"total_amount": "26.68"}})
    assert resp.status_code == 200
    body = resp.json()
    assert body["can_approve"] is True
    assert body["validation"]["is_valid"] is True
    assert body["current"]["total_amount"] == "26.68"
    assert body["original"]["total_amount"] == "99.00"  # original AI output untouched
    [c] = body["corrections"]
    assert (c["field_name"], c["original_value"], c["previous_value"], c["corrected_value"]) == (
        "total_amount",
        "99.00",
        "99.00",
        "26.68",
    )
    assert c["reviewer_id"] == "user_A"
    assert c["reviewed_at"]
    record = env.repo.get(doc_id)
    assert record is not None
    assert record.status is DocumentStatus.REVIEW_REQUIRED  # saving never approves
    assert record.extraction is not None
    assert record.extraction["document"]["total_amount"] == "99.00"


def test_second_correction_records_previous_value(env: Env) -> None:
    doc_id = bad_total(env)
    env.send("PATCH", f"/review/{doc_id}", {"fields": {"total_amount": "50.00"}})
    body = env.send("PATCH", f"/review/{doc_id}", {"fields": {"total_amount": "26.68"}}).json()
    assert [
        (c["previous_value"], c["corrected_value"], c["original_value"])
        for c in body["corrections"]
    ] == [
        ("99.00", "50.00", "99.00"),
        ("50.00", "26.68", "99.00"),
    ]


def test_unchanged_values_create_no_audit_entry(env: Env) -> None:
    doc_id = bad_total(env)
    body = env.send(
        "PATCH", f"/review/{doc_id}", {"fields": {"merchant_name": "Maple Leaf Cafe"}}
    ).json()
    assert body["corrections"] == []


@pytest.mark.parametrize(
    "fields",
    [
        {"document_date": "not-a-date"},
        {"total_amount": "abc"},
        {"missing_fields": []},
        {"user_id": "x"},
    ],
)
def test_invalid_corrections_rejected(env: Env, fields: dict[str, object]) -> None:
    doc_id = bad_total(env)
    resp = env.send("PATCH", f"/review/{doc_id}", {"fields": fields})
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] in {"invalid_correction", "validation_error"}


def test_cannot_correct_documents_not_in_review(env: Env) -> None:
    doc_id = env.add(status=DocumentStatus.VALID)
    assert (
        env.send("PATCH", f"/review/{doc_id}", {"fields": {"total_amount": "1"}}).status_code == 409
    )


def test_approval_blocked_while_invalid(env: Env) -> None:
    doc_id = bad_total(env)
    resp = env.send("POST", f"/review/{doc_id}/approve")
    assert resp.status_code == 409
    body = resp.json()
    assert body["error"]["code"] == "conflict"
    assert body["validation"]["is_valid"] is False
    assert env.writer.rows == []
    record = env.repo.get(doc_id)
    assert record is not None
    assert record.status is DocumentStatus.REVIEW_REQUIRED


def test_approve_after_correction_loads_corrected_record(env: Env) -> None:
    doc_id = bad_total(env)
    env.send("PATCH", f"/review/{doc_id}", {"fields": {"total_amount": "26.68"}})
    resp = env.send("POST", f"/review/{doc_id}/approve")
    assert resp.status_code == 200
    assert resp.json()["document"]["status"] == "APPROVED"

    [rows] = env.writer.rows
    assert rows.transaction is not None
    assert rows.transaction["total_amount"] == "26.68"
    assert rows.transaction["record_source"] == "REVIEWED"
    assert rows.transaction["approved_by"] == "user_A"
    assert rows.document["processing_status"] == "APPROVED"
    assert rows.document["review_required"] is True
    actions = [(r["action"], r["field_name"]) for r in rows.review_records]
    assert actions == [("CORRECTION", "total_amount"), ("APPROVE", None)]
    assert rows.review_records[0]["original_value"] == "99.00"

    record = env.repo.get(doc_id)
    assert record is not None
    assert record.status is DocumentStatus.APPROVED
    assert (record.model_extra or {})["approved_by"] == "user_A"
    assert record.history[-1]["status"] == "APPROVED"
    # Approving twice is refused.
    assert env.send("POST", f"/review/{doc_id}/approve").status_code == 409


def test_approve_fails_cleanly_when_bigquery_is_down(env: Env) -> None:
    doc_id = bad_total(env)
    env.send("PATCH", f"/review/{doc_id}", {"fields": {"total_amount": "26.68"}})
    env.writer.fail = True
    resp = env.send("POST", f"/review/{doc_id}/approve")
    assert resp.status_code == 503
    record = env.repo.get(doc_id)
    assert record is not None
    assert record.status is DocumentStatus.REVIEW_REQUIRED


def test_reject_requires_reason(env: Env) -> None:
    doc_id = bad_total(env)
    assert env.send("POST", f"/review/{doc_id}/reject", {"reason": ""}).status_code == 422
    assert env.send("POST", f"/review/{doc_id}/reject", {}).status_code == 422


def test_reject_records_reason_and_audit(env: Env) -> None:
    doc_id = bad_total(env)
    resp = env.send("POST", f"/review/{doc_id}/reject", {"reason": "Personal expense"})
    assert resp.status_code == 200
    [rows] = env.writer.rows
    assert rows.transaction is None
    assert rows.document["processing_status"] == "REJECTED"
    assert rows.review_records[-1]["action"] == "REJECT"
    assert rows.review_records[-1]["reason"] == "Personal expense"
    record = env.repo.get(doc_id)
    assert record is not None
    assert record.status is DocumentStatus.REJECTED
    assert (record.model_extra or {})["rejection_reason"] == "Personal expense"


def test_duplicates_can_be_rejected_but_valid_cannot(env: Env) -> None:
    dup = env.add(status=DocumentStatus.DUPLICATE)
    assert (
        env.send("POST", f"/review/{dup}/reject", {"reason": "duplicate upload"}).status_code == 200
    )
    valid = env.add(status=DocumentStatus.VALID)
    assert env.send("POST", f"/review/{valid}/reject", {"reason": "nope"}).status_code == 409


@pytest.mark.parametrize(
    ("method", "suffix", "body"),
    [
        ("GET", "", None),
        ("PATCH", "", {"fields": {"total_amount": "1"}}),
        ("POST", "/approve", None),
        ("POST", "/reject", {"reason": "not mine"}),
    ],
)
def test_cannot_review_other_users_documents(
    env: Env, method: str, suffix: str, body: object
) -> None:
    other = bad_total(env, "user_B")
    resp = env.send(method, f"/review/{other}{suffix}", body)
    assert resp.status_code == 404
    record = env.repo.get(other)
    assert record is not None
    assert record.status is DocumentStatus.REVIEW_REQUIRED
    assert "review" not in (record.model_extra or {})
    assert env.writer.rows == []


def test_opening_review_rechecks_against_current_rules(env: Env) -> None:
    """A document held for an unsupported currency becomes approvable once the rule changes."""
    from receipt_api.review_service import ReviewService
    from receipt_shared.validation import DocumentValidator, ValidationConfig

    doc_id = env.add("user_A", DocumentStatus.REVIEW_REQUIRED, doc=document(currency="PKR"))
    stored = env.repo.get(doc_id)
    assert stored is not None
    assert stored.validation is not None
    assert stored.validation["validation_errors"][0]["code"] == "UNSUPPORTED_CURRENCY"
    assert env.get(f"/review/{doc_id}").json()["can_approve"] is False

    env.app.state.review_service = ReviewService(
        repository=env.repo,
        validator=DocumentValidator(
            ValidationConfig(supported_currencies=frozenset({"CAD", "PKR"}))
        ),
        writer=env.writer,
    )
    body = env.get(f"/review/{doc_id}").json()
    assert body["can_approve"] is True
    assert body["validation"]["is_valid"] is True
    assert env.send("POST", f"/review/{doc_id}/approve").status_code == 200
    assert env.writer.rows[-1].transaction is not None
    assert env.writer.rows[-1].transaction["currency"] == "PKR"


# --- concurrency & audit visibility ------------------------------------------------------------
def test_stale_save_is_refused(env: Env) -> None:
    from receipt_api.review_service import ReviewConflictError

    doc_id = bad_total(env)
    service = env.app.state.review_service
    stale = env.repo.get(doc_id)
    assert stale is not None
    env.send("PATCH", f"/review/{doc_id}", {"fields": {"total_amount": "50.00"}})  # another tab
    with pytest.raises(ReviewConflictError):
        service.save_corrections(stale, reviewer_id="user_A", fields={"total_amount": "26.68"})
    record = env.repo.get(doc_id)
    assert record is not None
    corrected = (record.model_extra or {})["review"]["corrected"]
    assert corrected["total_amount"] == "50.00"  # the other tab's edit was not overwritten


def test_approve_racing_reject_keeps_bigquery_consistent(env: Env) -> None:
    from receipt_api.review_service import ReviewConflictError

    doc_id = bad_total(env)
    env.send("PATCH", f"/review/{doc_id}", {"fields": {"total_amount": "26.68"}})
    service = env.app.state.review_service
    stale = env.repo.get(doc_id)
    assert stale is not None
    # Rejected in another tab first...
    assert (
        env.send("POST", f"/review/{doc_id}/reject", {"reason": "Personal expense"}).status_code
        == 200
    )
    # ...then the stale approve arrives: its BigQuery write happens, but it loses the race.
    with pytest.raises(ReviewConflictError):
        service.approve(stale, reviewer_id="user_A")
    record = env.repo.get(doc_id)
    assert record is not None
    assert record.status is DocumentStatus.REJECTED
    last = env.writer.rows[-1]  # resynced to the winner
    assert last.document["processing_status"] == "REJECTED"
    assert last.transaction is None
    assert last.review_records[-1]["action"] == "REJECT"
    assert last.review_records[-1]["reason"] == "Personal expense"


def test_conflicts_return_409_with_reload_message(env: Env) -> None:
    doc_id = bad_total(env)
    env.send("PATCH", f"/review/{doc_id}", {"fields": {"total_amount": "26.68"}})
    original_get = env.repo.get

    def stale_get(document_id: str) -> object:
        record = original_get(document_id)
        env.repo.update(document_id, {"touched": True})  # someone writes right after our read
        return record

    env.repo.get = stale_get  # type: ignore[method-assign]
    resp = env.send("POST", f"/review/{doc_id}/approve")
    env.repo.get = original_get  # type: ignore[method-assign]
    assert resp.status_code == 409
    assert "Reload" in resp.json()["error"]["message"]
    record = env.repo.get(doc_id)
    assert record is not None
    assert record.status is DocumentStatus.REVIEW_REQUIRED


def test_document_detail_shows_decision_and_corrections(env: Env) -> None:
    doc_id = bad_total(env)
    env.send("PATCH", f"/review/{doc_id}", {"fields": {"total_amount": "26.68"}})
    env.send("POST", f"/review/{doc_id}/approve")
    review = env.get(f"/documents/{doc_id}").json()["review"]
    assert review["decision"]["action"] == "APPROVED"
    assert review["decision"]["by"] == "user_A"
    assert [c["field_name"] for c in review["corrections"]] == ["total_amount"]

    rejected = bad_total(env)
    env.send("POST", f"/review/{rejected}/reject", {"reason": "Not a business expense"})
    review = env.get(f"/documents/{rejected}").json()["review"]
    assert review["decision"] == {
        "action": "REJECTED",
        "by": "user_A",
        "at": review["decision"]["at"],
        "reason": "Not a business expense",
    }
    assert env.get(f"/documents/{env.add()}").json()["review"] is None
