from collections.abc import Callable
from datetime import date as _date
from decimal import Decimal

import pytest

from receipt_shared.models.extraction import ExtractedDocument, LineItem
from receipt_shared.models.validation import Severity, ValidationCode
from receipt_shared.validation import ValidationConfig
from receipt_shared.validation.rules import line_items, totals

TODAY = _date(2026, 11, 9)  # must match conftest
DocFactory = Callable[..., ExtractedDocument]

D = Decimal


# --- totals ------------------------------------------------------------------------------------
def test_standard_layout_adds_up(make_doc: DocFactory, cfg: ValidationConfig) -> None:
    assert totals(make_doc(), cfg, TODAY) == []  # 23.20 + 3.48 = 26.68


def test_within_tolerance_is_accepted(make_doc: DocFactory, cfg: ValidationConfig) -> None:
    assert totals(make_doc(total_amount=D("26.70")), cfg, TODAY) == []  # 0.02 cash rounding


def test_just_outside_tolerance_is_rejected(make_doc: DocFactory, cfg: ValidationConfig) -> None:
    [issue] = totals(make_doc(total_amount=D("26.71")), cfg, TODAY)
    assert issue.code is ValidationCode.TOTAL_MISMATCH
    assert issue.severity is Severity.ERROR


def test_tolerance_is_configurable(make_doc: DocFactory) -> None:
    loose = ValidationConfig(money_tolerance=D("0.10"))
    assert totals(make_doc(total_amount=D("26.75")), loose, TODAY) == []


def test_mismatch_message_explains_the_numbers(make_doc: DocFactory, cfg: ValidationConfig) -> None:
    [issue] = totals(make_doc(total_amount=D("30.00")), cfg, TODAY)
    assert "23.20 CAD" in issue.message
    assert "3.48 CAD" in issue.message
    assert "26.68 CAD" in issue.message
    assert "30.00 CAD" in issue.message
    assert "difference 3.32 CAD" in issue.message
    assert set(issue.fields) == {"subtotal", "tax_amount", "total_amount"}


def test_discount_is_subtracted(make_doc: DocFactory, cfg: ValidationConfig) -> None:
    doc = make_doc(discount_amount=D("5.00"), total_amount=D("21.68"))
    assert totals(doc, cfg, TODAY) == []


def test_negative_discount_is_treated_as_reduction(
    make_doc: DocFactory, cfg: ValidationConfig
) -> None:
    doc = make_doc(discount_amount=D("-5.00"), total_amount=D("21.68"))
    assert totals(doc, cfg, TODAY) == []


def test_discount_already_in_subtotal_is_accepted(
    make_doc: DocFactory, cfg: ValidationConfig
) -> None:
    doc = make_doc(discount_amount=D("5.00"), total_amount=D("26.68"))
    assert totals(doc, cfg, TODAY) == []


def test_tax_inclusive_layout_is_accepted_with_warning(
    make_doc: DocFactory, cfg: ValidationConfig
) -> None:
    # European style: prices include VAT, the receipt shows the VAT portion separately.
    doc = make_doc(
        currency="EUR", subtotal=D("119.00"), tax_amount=D("19.00"), total_amount=D("119.00")
    )
    [issue] = totals(doc, cfg, TODAY)
    assert issue.code is ValidationCode.TAX_INCLUDED_IN_SUBTOTAL
    assert issue.severity is Severity.WARNING


def test_zero_tax_is_fine(make_doc: DocFactory, cfg: ValidationConfig) -> None:
    doc = make_doc(subtotal=D("5.95"), tax_amount=D("0"), total_amount=D("5.95"))
    assert totals(doc, cfg, TODAY) == []


def test_missing_tax_is_not_assumed_zero_when_totals_differ(
    make_doc: DocFactory, cfg: ValidationConfig
) -> None:
    [issue] = totals(make_doc(tax_amount=None), cfg, TODAY)  # 23.20 vs 26.68
    assert issue.code is ValidationCode.TOTAL_MISMATCH
    assert "No tax amount was found" in issue.message
    assert "tax_amount" not in issue.fields


def test_missing_tax_ok_when_subtotal_equals_total(
    make_doc: DocFactory, cfg: ValidationConfig
) -> None:
    doc = make_doc(tax_amount=None, total_amount=D("23.20"))
    assert totals(doc, cfg, TODAY) == []


def test_missing_subtotal_cannot_be_verified(make_doc: DocFactory, cfg: ValidationConfig) -> None:
    [issue] = totals(make_doc(subtotal=None), cfg, TODAY)
    assert issue.code is ValidationCode.TOTALS_NOT_VERIFIABLE
    assert issue.severity is Severity.WARNING


def test_missing_total_is_left_to_required_rule(
    make_doc: DocFactory, cfg: ValidationConfig
) -> None:
    assert totals(make_doc(total_amount=None), cfg, TODAY) == []


def test_yen_uses_one_yen_tolerance(make_doc: DocFactory, cfg: ValidationConfig) -> None:
    doc = make_doc(currency="JPY", subtotal=D("1500"), tax_amount=D("150"), total_amount=D("1651"))
    assert totals(doc, cfg, TODAY) == []  # minor unit 1 JPY > 0.02 configured
    doc = make_doc(currency="JPY", subtotal=D("1500"), tax_amount=D("150"), total_amount=D("1652"))
    assert totals(doc, cfg, TODAY) != []


# --- line items --------------------------------------------------------------------------------
def li(total: str | None, qty: str | None = "1", unit: str | None = None) -> LineItem:
    return LineItem(
        description="x",
        quantity=D(qty) if qty else None,
        unit_price=D(unit) if unit else (D(total) if total else None),
        total_price=D(total) if total else None,
    )


def test_line_items_match_subtotal(make_doc: DocFactory, cfg: ValidationConfig) -> None:
    assert line_items(make_doc(), cfg, TODAY) == []


def test_line_items_mismatch_is_a_warning(make_doc: DocFactory, cfg: ValidationConfig) -> None:
    doc = make_doc(line_items=[li("10.50"), li("3.75")])  # sandwich missing
    [issue] = line_items(doc, cfg, TODAY)
    assert issue.code is ValidationCode.LINE_ITEMS_MISMATCH
    assert issue.severity is Severity.WARNING
    assert "14.25 CAD" in issue.message


def test_line_items_may_match_total_when_prices_include_tax(
    make_doc: DocFactory, cfg: ValidationConfig
) -> None:
    doc = make_doc(line_items=[li("20.00"), li("6.68")])
    assert line_items(doc, cfg, TODAY) == []


def test_line_items_may_be_before_discount(make_doc: DocFactory, cfg: ValidationConfig) -> None:
    doc = make_doc(
        discount_amount=D("5.00"),
        subtotal=D("23.20"),
        total_amount=D("21.68"),
        line_items=[li("18.20")],  # matches subtotal - discount
    )
    assert line_items(doc, cfg, TODAY) == []


def test_line_sum_skipped_when_a_line_total_is_missing(
    make_doc: DocFactory, cfg: ValidationConfig
) -> None:
    doc = make_doc(line_items=[li("1.00"), li(None, qty=None)])
    assert line_items(doc, cfg, TODAY) == []


def test_quantity_times_price_checked_per_line(make_doc: DocFactory, cfg: ValidationConfig) -> None:
    doc = make_doc(
        line_items=[
            li("10.50", qty="2", unit="5.25"),
            li("4.00", qty="1", unit="3.75"),  # wrong
            li("8.70", qty="1", unit="8.95"),  # wrong
        ]
    )
    issues = line_items(doc, cfg, TODAY)
    [arith] = [i for i in issues if i.code is ValidationCode.LINE_ITEM_ARITHMETIC]
    assert "line(s) 2, 3" in arith.message
    assert arith.severity is Severity.WARNING


def test_no_line_items_nothing_to_check(make_doc: DocFactory, cfg: ValidationConfig) -> None:
    assert line_items(make_doc(line_items=[]), cfg, TODAY) == []


@pytest.mark.parametrize("tol", ["0.05", "0.50"])
def test_line_tolerance_is_configurable(make_doc: DocFactory, tol: str) -> None:
    doc = make_doc(line_items=[li("23.40")])  # 0.20 off subtotal
    issues = line_items(doc, ValidationConfig(line_item_tolerance=D(tol)), TODAY)
    assert (issues == []) is (tol == "0.50")
