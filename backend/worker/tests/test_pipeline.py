from datetime import UTC, datetime, timedelta
from decimal import Decimal

from receipt_shared.extraction.errors import ModelCallError, ModelResponseError, RateLimitedError
from receipt_shared.models.enums import DocumentStatus
from receipt_shared.repository import ClaimOutcome

from .conftest import USER, Env, good_document, png


def statuses(env: Env, doc_id: str) -> list[str]:
    record = env.repo.get(doc_id)
    assert record is not None
    return [h["status"] for h in record.history]


# --- happy path --------------------------------------------------------------------------------
def test_valid_document_end_to_end(env: Env) -> None:
    doc_id, event = env.upload()
    outcome = env.processor.handle(event)

    assert (outcome.http_status, outcome.result, outcome.status) == (
        200,
        "processed",
        DocumentStatus.VALID,
    )
    record = env.repo.get(doc_id)
    assert record is not None
    assert record.status is DocumentStatus.VALID
    assert statuses(env, doc_id) == ["UPLOADED", "PROCESSING", "EXTRACTED", "VALIDATING", "VALID"]
    assert record.object_generation == 1
    assert record.processing_attempts == 1
    assert record.file_sha256
    assert len(record.file_sha256) == 64
    assert record.model_version == "gemini-test-001"
    assert record.extraction is not None
    assert record.extraction["document"]["total_amount"] == "26.68"
    assert record.validation is not None
    assert record.validation["validation_status"] == "VALID"
    assert record.lease_expires_at is None
    assert record.uploaded_at
    assert record.processing_started_at
    assert record.extracted_at
    assert record.completed_at
    assert record.processing_duration_ms is not None
    assert (record.merchant_key, record.total_amount, record.document_date) == (
        "mapleleafcafe",
        "26.68",
        "2026-03-14",
    )
    assert env.sink.loaded == [doc_id]


def test_invalid_document_goes_to_review(env: Env) -> None:
    env.extractor.default = good_document(total_amount=Decimal("99.00"))
    doc_id, event = env.upload()
    outcome = env.processor.handle(event)
    assert outcome.status is DocumentStatus.REVIEW_REQUIRED
    record = env.repo.get(doc_id)
    assert record is not None
    assert record.validation is not None
    assert [e["code"] for e in record.validation["validation_errors"]] == ["TOTAL_MISMATCH"]
    assert "total_amount" in record.validation["failed_fields"]
    assert env.sink.loaded == []  # only VALID records are loaded


def test_same_file_uploaded_twice_is_duplicate(env: Env) -> None:
    data = png("white")
    first, e1 = env.upload(data)
    second, e2 = env.upload(data)
    assert env.processor.handle(e1).status is DocumentStatus.VALID
    outcome = env.processor.handle(e2)
    assert outcome.status is DocumentStatus.DUPLICATE
    record = env.repo.get(second)
    assert record is not None
    assert record.validation is not None
    assert record.validation["duplicate_of"] == [first]
    assert env.sink.loaded == [first]


def test_lookalike_from_different_file_goes_to_review(env: Env) -> None:
    _, e1 = env.upload(png("white"))
    second, e2 = env.upload(png("gray"))
    env.processor.handle(e1)
    assert env.processor.handle(e2).status is DocumentStatus.REVIEW_REQUIRED
    record = env.repo.get(second)
    assert record is not None
    assert record.validation is not None
    assert record.validation["duplicate_status"] == "POSSIBLE_DUPLICATE"


def test_other_users_identical_file_is_not_a_duplicate(env: Env) -> None:
    data = png()
    _, e1 = env.upload(data, user="user_A")
    _, e2 = env.upload(data, user="user_B")
    env.processor.handle(e1)
    assert env.processor.handle(e2).status is DocumentStatus.VALID


# --- idempotency -------------------------------------------------------------------------------
def test_replayed_event_after_completion_is_acknowledged_without_work(env: Env) -> None:
    doc_id, event = env.upload()
    env.processor.handle(event)
    before = env.repo.get(doc_id)
    outcome = env.processor.handle(event)
    assert (outcome.http_status, outcome.result) == (200, ClaimOutcome.ALREADY_DONE.value)
    assert env.extractor.calls == [doc_id]  # Gemini called once
    assert env.sink.loaded == [doc_id]  # loaded once
    assert env.repo.get(doc_id) == before


def test_replay_while_another_delivery_holds_the_lease_is_retried_later(env: Env) -> None:
    doc_id, event = env.upload()
    env.repo.claim(doc_id, object_name=event.name, generation=1, lease_seconds=300, max_attempts=3)
    outcome = env.processor.handle(event)
    assert (outcome.http_status, outcome.result) == (429, "in_progress")
    assert env.extractor.calls == []


def test_crashed_attempt_is_retaken_after_lease_expiry(env: Env) -> None:
    doc_id, event = env.upload()
    env.repo.claim(doc_id, object_name=event.name, generation=1, lease_seconds=300, max_attempts=3)
    env.repo.update(doc_id, {"lease_expires_at": datetime.now(UTC) - timedelta(seconds=1)})
    outcome = env.processor.handle(event)
    assert outcome.status is DocumentStatus.VALID
    record = env.repo.get(doc_id)
    assert record is not None
    assert record.processing_attempts == 2


def test_stored_extraction_is_reused_not_overwritten(env: Env, monkeypatch: object) -> None:
    doc_id, event = env.upload()
    calls = {"n": 0}
    real_validate = env.validator.validate

    def flaky_validate(*args: object, **kwargs: object) -> object:
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("crash after extraction")
        return real_validate(*args, **kwargs)  # type: ignore[arg-type]

    env.validator.validate = flaky_validate  # type: ignore[method-assign]
    first = env.processor.handle(event)
    assert (first.http_status, first.result) == (500, "retry")
    stored = env.repo.get(doc_id)
    assert stored is not None
    assert stored.extraction is not None
    original = stored.extraction

    env.extractor.default = good_document(merchant_name="SOMETHING ELSE")
    second = env.processor.handle(event)
    assert second.status is DocumentStatus.VALID
    final = env.repo.get(doc_id)
    assert final is not None
    assert env.extractor.calls == [doc_id]  # Gemini not called again
    assert final.extraction == original  # original AI output untouched


def test_new_generation_of_finished_document_is_ignored(env: Env) -> None:
    doc_id, event = env.upload()
    env.processor.handle(event)
    outcome = env.processor.handle(env.event(event.name, generation=2))
    assert outcome.result == ClaimOutcome.STALE_GENERATION.value
    assert env.extractor.calls == [doc_id]


# --- failures ----------------------------------------------------------------------------------
def test_transient_gemini_error_is_retried_then_succeeds(env: Env) -> None:
    env.extractor.outcomes = [RateLimitedError("quota", retryable=True, status_code=429)]
    doc_id, event = env.upload()

    first = env.processor.handle(event)
    assert (first.http_status, first.result) == (503, "retry")
    record = env.repo.get(doc_id)
    assert record is not None
    assert record.status is DocumentStatus.PROCESSING
    assert record.lease_expires_at is None  # released so the redelivery can claim it
    assert record.last_error is not None
    assert record.last_error["retryable"] is True

    second = env.processor.handle(event)
    assert second.status is DocumentStatus.VALID
    final = env.repo.get(doc_id)
    assert final is not None
    assert final.processing_attempts == 2
    assert final.last_error is None


def test_gives_up_after_max_attempts(env: Env) -> None:
    env.extractor.outcomes = [ModelCallError("down", retryable=True, status_code=503)] * 3
    doc_id, event = env.upload()
    assert [env.processor.handle(event).http_status for _ in range(3)] == [503, 503, 503]
    outcome = env.processor.handle(event)
    assert (outcome.http_status, outcome.result) == (200, ClaimOutcome.GAVE_UP.value)
    record = env.repo.get(doc_id)
    assert record is not None
    assert record.status is DocumentStatus.FAILED
    assert record.last_error is not None
    assert record.last_error["code"] == "too_many_attempts"
    # Further deliveries are acknowledged without work.
    assert env.processor.handle(event).result == ClaimOutcome.ALREADY_DONE.value


def test_permanent_gemini_error_fails_without_retry(env: Env) -> None:
    env.extractor.outcomes = [
        ModelResponseError("Gemini declined to answer (finish_reason=SAFETY).")
    ]
    doc_id, event = env.upload()
    outcome = env.processor.handle(event)
    assert (outcome.http_status, outcome.status) == (200, DocumentStatus.FAILED)
    record = env.repo.get(doc_id)
    assert record is not None
    assert record.validation is not None
    assert record.validation["validation_status"] == "PROCESSING_FAILED"
    assert record.last_error is not None
    assert record.last_error["code"] == "invalid_model_response"
    assert statuses(env, doc_id)[-1] == "FAILED"


def test_non_retryable_api_error_fails(env: Env) -> None:
    env.extractor.outcomes = [ModelCallError("forbidden", retryable=False, status_code=403)]
    _, event = env.upload()
    assert env.processor.handle(event).status is DocumentStatus.FAILED


def test_file_with_wrong_size_fails_integrity_check(env: Env) -> None:
    doc_id, event = env.upload()
    env.storage.put(event.name, png() + b"tampered")
    outcome = env.processor.handle(event)
    assert outcome.status is DocumentStatus.FAILED
    record = env.repo.get(doc_id)
    assert record is not None
    assert record.last_error is not None
    assert record.last_error["code"] == "integrity_check_failed"
    assert env.extractor.calls == []


def test_spoofed_content_fails_integrity_check(env: Env) -> None:
    data = b"%PDF-1.7 not really a png" + b"\x00" * 40
    doc_id, event = env.upload(data)
    outcome = env.processor.handle(event)
    assert outcome.status is DocumentStatus.FAILED
    record = env.repo.get(doc_id)
    assert record is not None
    assert record.last_error is not None
    assert record.last_error["code"] == "unsupported_file_type"


def test_missing_object_fails(env: Env) -> None:
    _doc_id, event = env.upload()
    del env.storage.objects[event.name]
    assert env.processor.handle(event).status is DocumentStatus.FAILED


# --- events that must be ignored ---------------------------------------------------------------
def test_unknown_document_is_ignored(env: Env) -> None:
    event = env.event(f"uploads/{USER}/nosuchdoc/receipt.png")
    outcome = env.processor.handle(event)
    assert (outcome.http_status, outcome.result) == (200, "unknown_document")
    assert env.storage.reads == 0


def test_object_not_matching_record_is_ignored(env: Env) -> None:
    doc_id, _ = env.upload()
    outcome = env.processor.handle(env.event(f"uploads/someone_else/{doc_id}/receipt.png"))
    assert outcome.result == "object_mismatch"
    assert env.extractor.calls == []


def test_non_upload_objects_other_buckets_and_event_types_are_ignored(env: Env) -> None:
    _, event = env.upload()
    assert env.processor.handle(env.event("processed/u/d/out.json")).result == "ignored_object"
    assert env.processor.handle(env.event(event.name, bucket="other")).result == "ignored_bucket"
    assert (
        env.processor.handle(
            env.event(event.name, event_type="google.cloud.storage.object.v1.deleted")
        ).result
        == "ignored_event_type"
    )
    assert env.extractor.calls == []
