from collections.abc import Callable
from datetime import date, timedelta
from datetime import date as _date

import pytest

from receipt_shared.models.extraction import ExtractedDocument
from receipt_shared.models.validation import Severity, ValidationCode
from receipt_shared.validation import ValidationConfig
from receipt_shared.validation.rules import (
    currency,
    dates,
    document_type,
    invoice_number,
    optional_fields,
    required_fields,
)

TODAY = _date(2026, 11, 9)  # must match conftest
DocFactory = Callable[..., ExtractedDocument]


def codes(issues: list) -> list[ValidationCode]:  # type: ignore[type-arg]
    return [i.code for i in issues]


# --- required fields ---------------------------------------------------------------------------
def test_complete_document_has_no_missing_required(
    make_doc: DocFactory, cfg: ValidationConfig
) -> None:
    assert required_fields(make_doc(), cfg, TODAY) == []


@pytest.mark.parametrize(
    "field", ["merchant_name", "document_date", "total_amount", "currency", "document_type"]
)
def test_each_required_field_is_enforced(
    make_doc: DocFactory, cfg: ValidationConfig, field: str
) -> None:
    [issue] = required_fields(make_doc(**{field: None}), cfg, TODAY)
    assert issue.code is ValidationCode.MISSING_REQUIRED_FIELD
    assert issue.severity is Severity.ERROR
    assert issue.fields == [field]


def test_blank_merchant_counts_as_missing(make_doc: DocFactory, cfg: ValidationConfig) -> None:
    assert codes(required_fields(make_doc(merchant_name="   "), cfg, TODAY)) == [
        ValidationCode.MISSING_REQUIRED_FIELD
    ]


# --- optional fields ---------------------------------------------------------------------------
def test_missing_optional_fields_are_warnings_only(
    make_doc: DocFactory, cfg: ValidationConfig
) -> None:
    doc = make_doc(document_number=None, merchant_address=None, payment_method=None, line_items=[])
    issues = optional_fields(doc, cfg, TODAY)
    assert {f for i in issues for f in i.fields} == {
        "document_number",
        "merchant_address",
        "payment_method",
        "line_items",
    }
    assert all(i.severity is Severity.WARNING for i in issues)


def test_discount_absence_is_not_reported(make_doc: DocFactory, cfg: ValidationConfig) -> None:
    assert optional_fields(make_doc(discount_amount=None), cfg, TODAY) == []


def test_invoice_without_due_date_is_warned(make_doc: DocFactory, cfg: ValidationConfig) -> None:
    issues = optional_fields(make_doc(document_type="invoice", due_date=None), cfg, TODAY)
    assert [i.fields for i in issues] == [["due_date"]]


def test_receipt_without_due_date_is_fine(make_doc: DocFactory, cfg: ValidationConfig) -> None:
    assert optional_fields(make_doc(due_date=None), cfg, TODAY) == []


# --- document type -----------------------------------------------------------------------------
@pytest.mark.parametrize("value", ["receipt", "invoice"])
def test_receipts_and_invoices_accepted(
    make_doc: DocFactory, cfg: ValidationConfig, value: str
) -> None:
    assert document_type(make_doc(document_type=value), cfg, TODAY) == []


@pytest.mark.parametrize("value", ["other", "bank_statement", "RECEIPT"])
def test_other_document_types_rejected(
    make_doc: DocFactory, cfg: ValidationConfig, value: str
) -> None:
    [issue] = document_type(make_doc(document_type=value), cfg, TODAY)
    assert issue.code is ValidationCode.INVALID_DOCUMENT_TYPE
    assert issue.severity is Severity.ERROR


def test_missing_type_is_left_to_required_rule(make_doc: DocFactory, cfg: ValidationConfig) -> None:
    assert document_type(make_doc(document_type=None), cfg, TODAY) == []


# --- invoice number ----------------------------------------------------------------------------
def test_invoice_without_number_is_warned(make_doc: DocFactory, cfg: ValidationConfig) -> None:
    [issue] = invoice_number(make_doc(document_type="invoice", document_number=None), cfg, TODAY)
    assert issue.code is ValidationCode.INVOICE_WITHOUT_NUMBER
    assert issue.severity is Severity.WARNING


def test_receipt_without_number_is_not_flagged_by_invoice_rule(
    make_doc: DocFactory, cfg: ValidationConfig
) -> None:
    assert invoice_number(make_doc(document_number=None), cfg, TODAY) == []


# --- currency ----------------------------------------------------------------------------------
def test_supported_currency_accepted(make_doc: DocFactory, cfg: ValidationConfig) -> None:
    assert currency(make_doc(currency="EUR"), cfg, TODAY) == []


def test_unsupported_currency_rejected(make_doc: DocFactory, cfg: ValidationConfig) -> None:
    [issue] = currency(make_doc(currency="XYZ"), cfg, TODAY)
    assert issue.code is ValidationCode.UNSUPPORTED_CURRENCY
    assert issue.severity is Severity.ERROR
    assert "CAD" in issue.message  # lists what is supported


def test_currency_list_comes_from_config(make_doc: DocFactory, cfg: ValidationConfig) -> None:
    narrow = ValidationConfig(supported_currencies=frozenset({"USD"}))
    assert currency(make_doc(currency="CAD"), narrow, TODAY) != []
    assert currency(make_doc(currency="CAD"), cfg, TODAY) == []


# --- dates -------------------------------------------------------------------------------------
def test_normal_date_ok(make_doc: DocFactory, cfg: ValidationConfig) -> None:
    assert dates(make_doc(), cfg, TODAY) == []


def test_tomorrow_is_within_clock_skew_tolerance(
    make_doc: DocFactory, cfg: ValidationConfig
) -> None:
    assert dates(make_doc(document_date=TODAY + timedelta(days=1)), cfg, TODAY) == []


def test_future_date_is_an_error(make_doc: DocFactory, cfg: ValidationConfig) -> None:
    [issue] = dates(make_doc(document_date=TODAY + timedelta(days=5)), cfg, TODAY)
    assert issue.code is ValidationCode.DATE_IN_FUTURE
    assert issue.severity is Severity.ERROR


def test_very_old_date_is_a_warning(make_doc: DocFactory, cfg: ValidationConfig) -> None:
    [issue] = dates(make_doc(document_date=date(2001, 1, 1)), cfg, TODAY)
    assert issue.code is ValidationCode.DATE_TOO_OLD
    assert issue.severity is Severity.WARNING


def test_due_date_before_issue_date_is_warned(make_doc: DocFactory, cfg: ValidationConfig) -> None:
    doc = make_doc(document_type="invoice", due_date=date(2026, 3, 1))
    [issue] = dates(doc, cfg, TODAY)
    assert issue.code is ValidationCode.DUE_DATE_BEFORE_DOCUMENT_DATE
    assert set(issue.fields) == {"due_date", "document_date"}


def test_missing_date_is_left_to_required_rule(make_doc: DocFactory, cfg: ValidationConfig) -> None:
    assert dates(make_doc(document_date=None), cfg, TODAY) == []
