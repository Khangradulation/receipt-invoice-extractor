from decimal import Decimal

import pytest

from benchmark.scoring import (
    compare_field,
    money_tolerance,
    norm_text,
    score_document,
    score_line_items,
)
from sample_truth import TRUTH, item

TOL = Decimal("0.01")


@pytest.mark.parametrize(
    ("truth", "pred", "outcome"),
    [
        (None, None, "correct"),
        (None, "R-1", "hallucinated"),
        ("R-1", None, "missed"),
        ("R-1", "r1", "correct"),
        ("R-1", "R-2", "wrong"),
        ("R-1", "", "missed"),
    ],
)
def test_null_handling_and_ids(truth: str | None, pred: str | None, outcome: str) -> None:
    assert compare_field("document_number", truth, pred, tolerance=TOL) == outcome


@pytest.mark.parametrize(
    ("truth", "pred", "ok"),
    [
        ("26.68", "26.68", True),
        ("26.68", "26.680", True),
        ("26.68", 26.68, True),
        ("26.68", "26.69", True),
        ("26.68", "26.70", False),
        ("0.00", None, False),
    ],
)
def test_money_tolerance(truth: str, pred: object, ok: bool) -> None:
    outcome = compare_field("total_amount", truth, pred, tolerance=TOL)
    assert (outcome == "correct") is ok


def test_zero_is_not_null() -> None:
    assert compare_field("tax_amount", "0.00", "0", tolerance=TOL) == "correct"
    assert compare_field("tax_amount", None, "0.00", tolerance=TOL) == "hallucinated"


def test_tolerance_uses_currency_minor_unit() -> None:
    assert money_tolerance("USD") == Decimal("0.01")
    assert money_tolerance("JPY") == Decimal("1")
    assert money_tolerance("USD", Decimal("0.05")) == Decimal("0.05")


def test_text_fields_ignore_case_and_punctuation() -> None:
    assert norm_text("Maple-Leaf  CAFE.") == "maple leaf cafe"
    assert (
        compare_field(
            "merchant_name", "Harbour Books & Coffee", "HARBOUR BOOKS AND COFFEE", tolerance=TOL
        )
        == "correct"
    )
    assert (
        compare_field("merchant_name", "Maple Leaf Cafe", "Blue Door Bistro", tolerance=TOL)
        == "wrong"
    )


def test_currency_and_dates_exact() -> None:
    assert compare_field("currency", "CAD", "cad", tolerance=TOL) == "correct"
    assert compare_field("document_date", "2026-03-14", "2026-03-14", tolerance=TOL) == "correct"
    assert compare_field("document_date", "2026-03-14", "2026-14-03", tolerance=TOL) == "wrong"


def test_line_items_matching() -> None:
    truth = [item("Latte", "10.50", "2", "5.25"), item("Muffin", "3.75"), item("Sandwich", "8.95")]
    pred = [
        item("Sandwich", "8.95"),
        item("Latte (large)", "10.50", "2", "5.25"),
        item("Tip", "2.00"),
    ]
    s = score_line_items(truth, pred, tolerance=TOL)
    assert (s.matched, s.truth_count, s.predicted_count) == (
        1,
        3,
        3,
    )  # "Latte (large)" < 0.8 similar
    pred[1]["description"] = "Latte"
    s = score_line_items(truth, pred, tolerance=TOL)
    assert s.matched == 2
    assert s.precision == pytest.approx(2 / 3)
    assert s.recall == pytest.approx(2 / 3)
    assert (s.quantity_correct, s.quantity_compared) == (1, 1)
    assert not s.exact


def test_line_items_need_matching_amounts() -> None:
    s = score_line_items([item("Latte", "10.50")], [item("Latte", "10.05")], tolerance=TOL)
    assert s.matched == 0


def test_empty_line_items() -> None:
    s = score_line_items([], [], tolerance=TOL)
    assert (s.precision, s.recall, s.exact) == (1.0, 1.0, True)


def test_perfect_document() -> None:
    s = score_document("d", TRUTH, dict(TRUTH))
    assert s.fields_correct == s.fields_compared == 13
    assert s.required_correct
    assert s.core_correct
    assert s.fully_correct
    assert s.differences == {}


def test_document_with_errors() -> None:
    pred = dict(TRUTH, total_amount="28.68", expense_category="groceries", due_date="2026-04-01")
    s = score_document("d", TRUTH, pred)
    assert not s.required_correct
    assert s.fields["due_date"] == "hallucinated"
    assert set(s.differences) == {"total_amount", "expense_category", "due_date"}
    assert s.differences["total_amount"] == {
        "truth": "26.68",
        "predicted": "28.68",
        "outcome": "wrong",
    }


def test_interpretive_fields_do_not_affect_core() -> None:
    pred = dict(
        TRUTH, expense_category="groceries", payment_method="debit_card", merchant_address="Halifax"
    )
    s = score_document("d", TRUTH, pred)
    assert s.core_correct


def test_failed_extraction_counts_as_missed() -> None:
    s = score_document("d", TRUTH, {})
    assert s.fields["total_amount"] == "missed"
    assert s.fields["due_date"] == "correct"  # nothing printed, nothing returned
    assert not s.required_correct
