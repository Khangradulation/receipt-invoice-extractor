import json
import logging
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from google.genai import errors as genai_errors
from google.genai import types

from receipt_shared.config import Settings
from receipt_shared.extraction import (
    PROMPT_VERSION,
    DocumentInput,
    ExtractionConfigError,
    GeminiExtractor,
    ModelCallError,
    ModelResponseError,
    ModelTimeoutError,
    RateLimitedError,
    build_client,
    inspect_document,
)
from receipt_shared.extraction.prompt import SYSTEM_INSTRUCTION

GOOD_ANSWER: dict[str, Any] = {
    "document_type": "receipt",
    "document_number": "R-10482",
    "document_date": "2026-03-14",
    "currency": "CAD",
    "merchant_name": "Maple Leaf Cafe",
    "merchant_address": "42 Harbour Street, Halifax",
    "subtotal": 23.2,
    "tax_amount": 3.48,
    "total_amount": 26.68,
    "payment_method": "credit_card",
    "line_items": [
        {"description": "Latte", "quantity": 2, "unit_price": 5.25, "total_price": 10.5}
    ],
    "expense_category": "meals",
}


def response(payload: dict[str, Any] | str | None = None, finish: str = "STOP") -> SimpleNamespace:
    text = payload if isinstance(payload, str) or payload is None else json.dumps(payload)
    return SimpleNamespace(
        text=text,
        candidates=[SimpleNamespace(finish_reason=types.FinishReason(finish))],
        model_version="gemini-test-001",
        usage_metadata=SimpleNamespace(
            prompt_token_count=1200,
            candidates_token_count=300,
            thoughts_token_count=None,
            total_token_count=1500,
        ),
    )


def api_error(code: int, headers: dict[str, str] | None = None) -> genai_errors.APIError:
    status = {429: "RESOURCE_EXHAUSTED", 400: "INVALID_ARGUMENT", 503: "UNAVAILABLE"}.get(code, "X")
    body = {"error": {"code": code, "message": "boom", "status": status}}
    resp = SimpleNamespace(headers=headers or {})
    cls = genai_errors.ClientError if code < 500 else genai_errors.ServerError
    return cls(code, body, resp)  # type: ignore[arg-type]


class FakeModels:
    def __init__(self, outcomes: list[Any]) -> None:
        self.outcomes = list(outcomes)
        self.calls: list[dict[str, Any]] = []

    def generate_content(self, *, model: str, contents: Any, config: Any) -> Any:
        self.calls.append({"model": model, "contents": contents, "config": config})
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


class FakeClient:
    def __init__(self, outcomes: list[Any]) -> None:
        self.models = FakeModels(outcomes)


@pytest.fixture
def document(settings: Settings, png_bytes: bytes) -> DocumentInput:
    return inspect_document(png_bytes, settings, filename="r.png")


def make(
    settings: Settings, outcomes: list[Any]
) -> tuple[GeminiExtractor, FakeClient, list[float]]:
    client = FakeClient(outcomes)
    sleeps: list[float] = []
    extractor = GeminiExtractor(settings, client=client, sleep=sleeps.append, rng=lambda: 0.5)
    return extractor, client, sleeps


def test_successful_extraction(settings: Settings, document: DocumentInput) -> None:
    extractor, client, sleeps = make(settings, [response(GOOD_ANSWER)])
    result = extractor.extract(document, document_id="doc-1")

    assert result.document.total_amount == Decimal("26.68")
    assert result.document.merchant_name == "Maple Leaf Cafe"
    assert "due_date" in result.document.missing_fields
    md = result.metadata
    assert (md.model, md.model_version, md.prompt_version) == (
        "gemini-test",
        "gemini-test-001",
        PROMPT_VERSION,
    )
    assert md.attempts == 1
    assert md.total_tokens == 1500
    assert md.finish_reason == "STOP"
    assert sleeps == []
    assert len(client.models.calls) == 1


def test_request_configuration(settings: Settings, document: DocumentInput) -> None:
    extractor, client, _ = make(settings, [response(GOOD_ANSWER)])
    extractor.extract(document)
    call = client.models.calls[0]
    cfg: types.GenerateContentConfig = call["config"]
    assert call["model"] == "gemini-test"
    assert cfg.temperature == 0.0
    assert cfg.response_mime_type == "application/json"
    assert cfg.response_schema is not None
    assert cfg.system_instruction == SYSTEM_INSTRUCTION
    doc_part, instruction = call["contents"]
    assert doc_part.inline_data.mime_type == "image/png"
    assert doc_part.inline_data.data == document.data
    assert "Extract" in instruction.text


def test_gcs_documents_are_sent_by_reference(settings: Settings, png_bytes: bytes) -> None:
    doc = inspect_document(png_bytes, settings, gcs_uri="gs://b/uploads/u/d/r.png")
    extractor, client, _ = make(settings, [response(GOOD_ANSWER)])
    extractor.extract(doc)
    part = client.models.calls[0]["contents"][0]
    assert part.file_data.file_uri == "gs://b/uploads/u/d/r.png"
    assert part.inline_data is None


def test_thinking_budget_is_configurable(settings: Settings, document: DocumentInput) -> None:
    extractor, client, _ = make(
        settings.model_copy(update={"gemini_thinking_budget": 0}), [response(GOOD_ANSWER)]
    )
    extractor.extract(document)
    assert client.models.calls[0]["config"].thinking_config.thinking_budget == 0


def test_transient_server_errors_are_retried(settings: Settings, document: DocumentInput) -> None:
    extractor, _, sleeps = make(settings, [api_error(503), api_error(500), response(GOOD_ANSWER)])
    result = extractor.extract(document)
    assert result.metadata.attempts == 3
    # Full jitter with rng=0.5: 0.5 * min(30, 1 * 2**n)
    assert sleeps == [0.5, 1.0]


def test_rate_limit_honours_retry_after(settings: Settings, document: DocumentInput) -> None:
    extractor, _, sleeps = make(
        settings, [api_error(429, {"retry-after": "7"}), response(GOOD_ANSWER)]
    )
    extractor.extract(document)
    assert sleeps == [7.0]


def test_rate_limit_exhaustion_raises_retryable_error(
    settings: Settings, document: DocumentInput
) -> None:
    extractor, client, sleeps = make(settings, [api_error(429)] * 4)
    with pytest.raises(RateLimitedError) as info:
        extractor.extract(document)
    assert info.value.retryable is True
    assert info.value.status_code == 429
    assert len(client.models.calls) == 4  # 1 + gemini_max_retries(3)
    assert len(sleeps) == 3


def test_backoff_is_capped(settings: Settings, document: DocumentInput) -> None:
    s = settings.model_copy(update={"gemini_max_retries": 6, "gemini_retry_max_delay_seconds": 4.0})
    extractor, _, sleeps = make(s, [api_error(503)] * 6 + [response(GOOD_ANSWER)])
    extractor.extract(document)
    assert max(sleeps) <= 4.0


def test_client_errors_are_not_retried(settings: Settings, document: DocumentInput) -> None:
    extractor, client, sleeps = make(settings, [api_error(400)])
    with pytest.raises(ModelCallError) as info:
        extractor.extract(document)
    assert info.value.retryable is False
    assert info.value.status_code == 400
    assert len(client.models.calls) == 1
    assert sleeps == []


def test_permission_errors_include_googles_reason(
    settings: Settings, document: DocumentInput
) -> None:
    body = {
        "error": {
            "code": 403,
            "status": "PERMISSION_DENIED",
            "message": "This API method requires billing to be enabled.",
            "details": [
                {"@type": "type.googleapis.com/google.rpc.ErrorInfo", "reason": "BILLING_DISABLED"}
            ],
        }
    }
    err = genai_errors.ClientError(403, body, SimpleNamespace(headers={}))  # type: ignore[arg-type]
    extractor, _, _ = make(settings, [err])
    with pytest.raises(ModelCallError) as info:
        extractor.extract(document)
    assert info.value.retryable is False
    assert "[BILLING_DISABLED] This API method requires billing" in info.value.message


def test_timeouts_are_retried(settings: Settings, document: DocumentInput) -> None:
    extractor, _, _ = make(
        settings, [httpx.ReadTimeout("slow"), httpx.ConnectError("down"), response(GOOD_ANSWER)]
    )
    assert extractor.extract(document).metadata.attempts == 3


def test_persistent_timeouts_raise_timeout_error(
    settings: Settings, document: DocumentInput
) -> None:
    extractor, _, _ = make(settings, [httpx.ReadTimeout("slow")] * 4)
    with pytest.raises(ModelTimeoutError) as info:
        extractor.extract(document)
    assert info.value.retryable is True


def test_malformed_json_is_retried_once(settings: Settings, document: DocumentInput) -> None:
    extractor, _, _ = make(settings, [response("not json"), response(GOOD_ANSWER)])
    assert extractor.extract(document).metadata.attempts == 2


def test_repeated_malformed_json_fails(settings: Settings, document: DocumentInput) -> None:
    extractor, client, _ = make(
        settings, [response("{"), response('{"total_amount": "abc"}'), response(GOOD_ANSWER)]
    )
    with pytest.raises(ModelResponseError):
        extractor.extract(document)
    assert len(client.models.calls) == 2


def test_empty_answer_is_retried(settings: Settings, document: DocumentInput) -> None:
    extractor, _, _ = make(settings, [response(None), response(GOOD_ANSWER)])
    assert extractor.extract(document).metadata.attempts == 2


@pytest.mark.parametrize("finish", ["SAFETY", "RECITATION", "MAX_TOKENS"])
def test_unusable_answers_fail_without_retry(
    settings: Settings, document: DocumentInput, finish: str
) -> None:
    extractor, client, _ = make(settings, [response(GOOD_ANSWER, finish=finish)])
    with pytest.raises(ModelResponseError, match=finish):
        extractor.extract(document)
    assert len(client.models.calls) == 1


def test_logs_contain_no_document_content(
    settings: Settings, document: DocumentInput, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    extractor, _, _ = make(settings, [api_error(503), response(GOOD_ANSWER)])
    extractor.extract(document, document_id="doc-xyz")
    records = [r for r in caplog.records if r.name == "receipt.extraction"]
    assert {r.getMessage() for r in records} >= {
        "gemini extraction started",
        "gemini attempt failed",
        "gemini extraction completed",
    }
    dumped = json.dumps([r.__dict__ for r in records], default=str)
    assert "doc-xyz" in dumped
    for secret in ("Maple Leaf Cafe", "26.68", "Harbour", "Latte", "R-10482"):
        assert secret not in dumped


def test_build_client_requires_project() -> None:
    with pytest.raises(ExtractionConfigError, match="GCP_PROJECT_ID"):
        build_client(Settings(_env_file=None, gcp_project_id=None))


def test_build_client_uses_vertex_with_timeout(settings: Settings) -> None:
    client = build_client(settings)
    api = client._api_client
    assert api.vertexai is True
    assert api.project == "test-project"
    assert api.location == "us-central1"
    assert api._http_options.timeout == 120_000


def test_prompt_separates_payment_terms_from_completed_payments() -> None:
    rule = SYSTEM_INSTRUCTION[SYSTEM_INSTRUCTION.index("9. payment_method") :]
    assert "actually made" in rule
    assert "Payment by bank transfer" in rule
    assert "payment_method is null" in rule
