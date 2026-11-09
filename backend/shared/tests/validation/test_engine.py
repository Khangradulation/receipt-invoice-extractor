from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from receipt_shared.config import Settings
from receipt_shared.models.enums import DuplicateStatus, ProcessingOutcome
from receipt_shared.models.extraction import ExtractedDocument
from receipt_shared.models.validation import Severity, ValidationCode, ValidationResult
from receipt_shared.validation import (
    RULES_VERSION,
    DocumentValidator,
    InMemoryDuplicateIndex,
    ValidationConfig,
    fingerprint,
)

DocFactory = Callable[..., ExtractedDocument]
TODAY = date(2026, 11, 9)
T0 = datetime(2026, 11, 9, 12, tzinfo=UTC)


def run(validator: DocumentValidator, doc: ExtractedDocument, **kwargs: object) -> ValidationResult:
    params: dict[str, object] = {
        "document_id": "doc-new",
        "user_id": "u1",
        "file_sha256": "hash-new",
        "created_at": T0 + timedelta(minutes=1),
        "today": TODAY,
    }
    params.update(kwargs)
    return validator.validate(doc, **params)  # type: ignore[arg-type]


def test_clean_document_is_valid(make_doc: DocFactory, cfg: ValidationConfig) -> None:
    result = run(DocumentValidator(cfg), make_doc())
    assert result.is_valid
    assert result.validation_status is ProcessingOutcome.VALID
    assert result.validation_errors == []
    assert result.failed_fields == []
    assert result.duplicate_status is DuplicateStatus.NOT_DUPLICATE
    assert result.rules_version == RULES_VERSION


def test_warnings_alone_keep_document_valid(make_doc: DocFactory, cfg: ValidationConfig) -> None:
    doc = make_doc(merchant_address=None, payment_method=None, line_items=[], document_number=None)
    result = run(DocumentValidator(cfg), doc)
    assert result.validation_status is ProcessingOutcome.VALID
    assert len(result.validation_warnings) == 4


def test_errors_route_to_review_with_failed_fields(
    make_doc: DocFactory, cfg: ValidationConfig
) -> None:
    doc = make_doc(merchant_name=None, total_amount=Decimal("99.00"))
    result = run(DocumentValidator(cfg), doc)
    assert not result.is_valid
    assert result.validation_status is ProcessingOutcome.REVIEW_REQUIRED
    assert {i.code for i in result.validation_errors} == {
        ValidationCode.MISSING_REQUIRED_FIELD,
        ValidationCode.TOTAL_MISMATCH,
    }
    assert result.failed_fields == ["merchant_name", "subtotal", "tax_amount", "total_amount"]
    assert all(i.severity is Severity.ERROR for i in result.validation_errors)


def test_extraction_warnings_are_carried_over(make_doc: DocFactory, cfg: ValidationConfig) -> None:
    result = run(
        DocumentValidator(cfg),
        make_doc(document_date=None),
        extraction_warnings=["document_date: '2026-02-30' is not a valid YYYY-MM-DD date"],
    )
    assert result.validation_status is ProcessingOutcome.REVIEW_REQUIRED
    [carried] = [
        w for w in result.validation_warnings if w.code is ValidationCode.EXTRACTION_WARNING
    ]
    assert "2026-02-30" in carried.message


def _index(make_doc: DocFactory, **overrides: object) -> InMemoryDuplicateIndex:
    return InMemoryDuplicateIndex(
        [
            fingerprint(
                document_id="doc-old",
                user_id="u1",
                file_sha256=str(overrides.pop("sha", "hash-old")),
                document=make_doc(**overrides),
                status="VALID",
                created_at=T0,
            )
        ]
    )


def test_exact_duplicate_outcome(make_doc: DocFactory, cfg: ValidationConfig) -> None:
    result = run(
        DocumentValidator(cfg), make_doc(), duplicate_index=_index(make_doc, sha="hash-new")
    )
    assert result.validation_status is ProcessingOutcome.DUPLICATE
    assert result.duplicate_status is DuplicateStatus.DUPLICATE
    assert result.duplicate_of == ["doc-old"]
    assert not result.is_valid


def test_possible_duplicate_goes_to_review(make_doc: DocFactory, cfg: ValidationConfig) -> None:
    result = run(DocumentValidator(cfg), make_doc(), duplicate_index=_index(make_doc))
    assert result.validation_status is ProcessingOutcome.REVIEW_REQUIRED
    assert result.duplicate_status is DuplicateStatus.POSSIBLE_DUPLICATE


def test_reviewer_can_acknowledge_possible_duplicate(
    make_doc: DocFactory, cfg: ValidationConfig
) -> None:
    result = run(
        DocumentValidator(cfg),
        make_doc(),
        duplicate_index=_index(make_doc),
        duplicate_acknowledged=True,
    )
    assert result.validation_status is ProcessingOutcome.VALID
    assert result.duplicate_status is DuplicateStatus.POSSIBLE_DUPLICATE  # still recorded
    assert any(w.code is ValidationCode.POSSIBLE_DUPLICATE for w in result.validation_warnings)


def test_acknowledgement_does_not_override_exact_file_duplicate(
    make_doc: DocFactory, cfg: ValidationConfig
) -> None:
    result = run(
        DocumentValidator(cfg),
        make_doc(),
        duplicate_index=_index(make_doc, sha="hash-new"),
        duplicate_acknowledged=True,
    )
    assert result.validation_status is ProcessingOutcome.DUPLICATE


def test_processing_failed_result() -> None:
    result = ValidationResult.processing_failed("Gemini declined to answer.", rules_version="v")
    assert result.validation_status is ProcessingOutcome.PROCESSING_FAILED
    assert not result.is_valid
    assert result.validation_errors[0].code is ValidationCode.PROCESSING_FAILED


def test_config_comes_from_settings(make_doc: DocFactory) -> None:
    settings = Settings(_env_file=None, money_tolerance=Decimal("1.00"), supported_currencies="CAD")
    validator = DocumentValidator(settings=settings)
    assert run(validator, make_doc(total_amount=Decimal("27.50"))).is_valid
    assert not run(validator, make_doc(currency="USD")).is_valid


def test_custom_rule_set(make_doc: DocFactory, cfg: ValidationConfig) -> None:
    validator = DocumentValidator(cfg, rules=())
    assert run(validator, make_doc(merchant_name=None)).is_valid


def test_result_round_trips_through_json(make_doc: DocFactory, cfg: ValidationConfig) -> None:
    # Persisted to Firestore as JSON; must survive serialisation unchanged.
    result = run(DocumentValidator(cfg), make_doc(total_amount=Decimal("30.00")))
    assert ValidationResult.model_validate_json(result.model_dump_json()) == result
