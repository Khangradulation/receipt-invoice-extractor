from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from receipt_shared.models.enums import DuplicateStatus
from receipt_shared.models.extraction import ExtractedDocument
from receipt_shared.models.validation import DocumentFingerprint, ValidationCode
from receipt_shared.validation import (
    InMemoryDuplicateIndex,
    check_duplicates,
    document_number_key,
    fingerprint,
    merchant_key,
)

DocFactory = Callable[..., ExtractedDocument]
T0 = datetime(2026, 11, 9, 12, 0, tzinfo=UTC)


def fp(
    make_doc: DocFactory,
    doc_id: str,
    *,
    sha: str = "hash-a",
    user: str = "u1",
    status: str = "VALID",
    at: datetime = T0,
    **overrides: object,
) -> DocumentFingerprint:
    return fingerprint(
        document_id=doc_id,
        user_id=user,
        file_sha256=sha,
        document=make_doc(**overrides),
        status=status,
        created_at=at,
    )


def later(minutes: int = 5) -> datetime:
    return T0 + timedelta(minutes=minutes)


# --- normalisation -----------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("a", "b"),
    [("Maple Leaf Cafe", "MAPLE LEAF CAFÉ"), ("Café Nero, Ltd.", "cafe nero ltd"), ("A&W", "a w")],
)
def test_merchant_key_ignores_case_accents_punctuation(a: str, b: str) -> None:
    assert merchant_key(a) == merchant_key(b)


@pytest.mark.parametrize(
    ("a", "b"), [("INV-0042", "inv 42"), ("R-10482", "r10482"), ("0088213", "88213")]
)
def test_document_number_key_normalises(a: str, b: str) -> None:
    assert document_number_key(a) == document_number_key(b)


def test_document_number_keys_distinguish_different_numbers() -> None:
    assert document_number_key("INV-0042") != document_number_key("INV-0043")
    assert document_number_key("A100") != document_number_key("A1000")


def test_empty_keys_are_none() -> None:
    assert merchant_key("  ...  ") is None
    assert document_number_key(None) is None


# --- exact file duplicates ---------------------------------------------------------------------
def test_same_file_is_duplicate(make_doc: DocFactory) -> None:
    index = InMemoryDuplicateIndex([fp(make_doc, "d1")])
    status, of, [issue] = check_duplicates(fp(make_doc, "d2", at=later()), index)
    assert status is DuplicateStatus.DUPLICATE
    assert of == ["d1"]
    assert issue.code is ValidationCode.DUPLICATE_FILE


def test_same_file_even_if_extraction_differs(make_doc: DocFactory) -> None:
    index = InMemoryDuplicateIndex([fp(make_doc, "d1", merchant_name="Other")])
    status, _, _ = check_duplicates(fp(make_doc, "d2", at=later()), index)
    assert status is DuplicateStatus.DUPLICATE


def test_document_does_not_match_itself(make_doc: DocFactory) -> None:
    index = InMemoryDuplicateIndex([fp(make_doc, "d1")])
    assert check_duplicates(fp(make_doc, "d1"), index)[0] is DuplicateStatus.NOT_DUPLICATE


def test_other_users_documents_are_never_matched(make_doc: DocFactory) -> None:
    index = InMemoryDuplicateIndex([fp(make_doc, "d1", user="someone-else")])
    assert (
        check_duplicates(fp(make_doc, "d2", at=later()), index)[0] is DuplicateStatus.NOT_DUPLICATE
    )


@pytest.mark.parametrize("status", ["REJECTED", "FAILED"])
def test_rejected_or_failed_documents_are_ignored(make_doc: DocFactory, status: str) -> None:
    index = InMemoryDuplicateIndex([fp(make_doc, "d1", status=status)])
    assert (
        check_duplicates(fp(make_doc, "d2", at=later()), index)[0] is DuplicateStatus.NOT_DUPLICATE
    )


def test_only_earlier_documents_count(make_doc: DocFactory) -> None:
    # d2 was uploaded later than d1; when d1 is (re)validated it must not be marked a duplicate.
    index = InMemoryDuplicateIndex([fp(make_doc, "d2", at=later())])
    assert check_duplicates(fp(make_doc, "d1"), index)[0] is DuplicateStatus.NOT_DUPLICATE


def test_simultaneous_uploads_mark_exactly_one_duplicate(make_doc: DocFactory) -> None:
    a, b = fp(make_doc, "aaa"), fp(make_doc, "bbb")  # same created_at
    index = InMemoryDuplicateIndex([a, b])
    results = {d.document_id: check_duplicates(d, index)[0] for d in (a, b)}
    assert results == {"aaa": DuplicateStatus.NOT_DUPLICATE, "bbb": DuplicateStatus.DUPLICATE}


# --- business-key look-alikes ------------------------------------------------------------------
def test_same_merchant_and_number_is_possible_duplicate(make_doc: DocFactory) -> None:
    index = InMemoryDuplicateIndex([fp(make_doc, "d1", sha="photo-1")])
    status, of, [issue] = check_duplicates(
        fp(make_doc, "d2", sha="photo-2", at=later(), document_number="r 10482"), index
    )
    assert status is DuplicateStatus.POSSIBLE_DUPLICATE
    assert of == ["d1"]
    assert issue.code is ValidationCode.POSSIBLE_DUPLICATE
    assert "document number" in issue.message


def test_different_document_numbers_are_not_duplicates(make_doc: DocFactory) -> None:
    index = InMemoryDuplicateIndex([fp(make_doc, "d1", sha="x")])
    current = fp(make_doc, "d2", sha="y", at=later(), document_number="R-10483")
    assert check_duplicates(current, index)[0] is DuplicateStatus.NOT_DUPLICATE


def test_no_numbers_same_merchant_date_total_is_possible(make_doc: DocFactory) -> None:
    index = InMemoryDuplicateIndex([fp(make_doc, "d1", sha="x", document_number=None)])
    current = fp(make_doc, "d2", sha="y", at=later(), document_number=None)
    status, _, [issue] = check_duplicates(current, index)
    assert status is DuplicateStatus.POSSIBLE_DUPLICATE
    assert "date, total and currency" in issue.message


@pytest.mark.parametrize(
    "change",
    [
        {"total_amount": Decimal("26.69")},
        {"document_date": date(2026, 3, 15)},
        {"currency": "USD"},
        {"merchant_name": "Another Cafe"},
    ],
)
def test_any_business_difference_means_not_duplicate(
    make_doc: DocFactory, change: dict[str, object]
) -> None:
    index = InMemoryDuplicateIndex([fp(make_doc, "d1", sha="x", document_number=None)])
    current = fp(make_doc, "d2", sha="y", at=later(), document_number=None, **change)
    assert check_duplicates(current, index)[0] is DuplicateStatus.NOT_DUPLICATE


def test_one_side_without_number_falls_back_to_full_key(make_doc: DocFactory) -> None:
    index = InMemoryDuplicateIndex([fp(make_doc, "d1", sha="x")])  # has number
    current = fp(make_doc, "d2", sha="y", at=later(), document_number=None)
    assert check_duplicates(current, index)[0] is DuplicateStatus.POSSIBLE_DUPLICATE


def test_missing_total_never_matches_on_business_key(make_doc: DocFactory) -> None:
    index = InMemoryDuplicateIndex(
        [fp(make_doc, "d1", sha="x", document_number=None, total_amount=None)]
    )
    current = fp(make_doc, "d2", sha="y", at=later(), document_number=None, total_amount=None)
    assert check_duplicates(current, index)[0] is DuplicateStatus.NOT_DUPLICATE


def test_exact_file_takes_precedence_over_lookalike(make_doc: DocFactory) -> None:
    index = InMemoryDuplicateIndex([fp(make_doc, "d1", sha="x"), fp(make_doc, "d0", sha="y")])
    status, of, _ = check_duplicates(fp(make_doc, "d2", sha="y", at=later()), index)
    assert status is DuplicateStatus.DUPLICATE
    assert of == ["d0"]
