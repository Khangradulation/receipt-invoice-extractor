from collections.abc import Callable
from datetime import date as _date
from decimal import Decimal

import pytest

from receipt_shared.models.extraction import ExtractedDocument
from receipt_shared.models.validation import Severity, ValidationCode
from receipt_shared.validation import ValidationConfig, minor_unit
from receipt_shared.validation.rules import amounts

TODAY = _date(2026, 11, 9)  # must match conftest
DocFactory = Callable[..., ExtractedDocument]

D = Decimal


def test_valid_amounts(make_doc: DocFactory, cfg: ValidationConfig) -> None:
    assert amounts(make_doc(), cfg, TODAY) == []


@pytest.mark.parametrize("field", ["total_amount", "subtotal", "tax_amount"])
def test_negative_amounts_are_errors(
    make_doc: DocFactory, cfg: ValidationConfig, field: str
) -> None:
    issues = amounts(make_doc(**{field: D("-1.00")}), cfg, TODAY)
    [neg] = [i for i in issues if i.code is ValidationCode.NEGATIVE_AMOUNT]
    assert neg.severity is Severity.ERROR
    assert neg.fields == [field]


def test_negative_discount_is_warning_and_treated_as_reduction(
    make_doc: DocFactory, cfg: ValidationConfig
) -> None:
    [issue] = amounts(make_doc(discount_amount=D("-2.00")), cfg, TODAY)
    assert issue.code is ValidationCode.NEGATIVE_DISCOUNT
    assert issue.severity is Severity.WARNING


def test_zero_total_is_warned(make_doc: DocFactory, cfg: ValidationConfig) -> None:
    codes = [i.code for i in amounts(make_doc(total_amount=D("0")), cfg, TODAY)]
    assert codes == [ValidationCode.ZERO_TOTAL]


def test_huge_amount_is_warned(make_doc: DocFactory, cfg: ValidationConfig) -> None:
    issues = amounts(make_doc(total_amount=D("2500000.00")), cfg, TODAY)
    assert [i.code for i in issues] == [ValidationCode.AMOUNT_TOO_LARGE]
    assert issues[0].severity is Severity.WARNING


def test_too_many_decimals_for_currency(make_doc: DocFactory, cfg: ValidationConfig) -> None:
    issues = amounts(make_doc(tax_amount=D("3.475")), cfg, TODAY)
    assert [i.code for i in issues] == [ValidationCode.TOO_MANY_DECIMALS]


def test_trailing_zero_float_form_is_not_too_many_decimals(
    make_doc: DocFactory, cfg: ValidationConfig
) -> None:
    # Gemini numbers arrive as e.g. Decimal("5809.0"); that is still a valid 2-decimal amount.
    assert amounts(make_doc(subtotal=D("23.2"), total_amount=D("26.680")), cfg, TODAY) == []


def test_yen_amounts_must_be_whole(make_doc: DocFactory, cfg: ValidationConfig) -> None:
    ok = make_doc(currency="JPY", subtotal=D("1500"), tax_amount=D("150"), total_amount=D("1650"))
    assert amounts(ok, cfg, TODAY) == []
    bad = make_doc(
        currency="JPY", subtotal=D("1500"), tax_amount=D("150.5"), total_amount=D("1650")
    )
    assert [i.code for i in amounts(bad, cfg, TODAY)] == [ValidationCode.TOO_MANY_DECIMALS]


@pytest.mark.parametrize(
    ("currency", "unit"),
    [("USD", "0.01"), ("JPY", "1"), ("KWD", "0.001"), (None, "0.01"), ("usd", "0.01")],
)
def test_minor_units(currency: str | None, unit: str) -> None:
    assert minor_unit(currency) == D(unit)
