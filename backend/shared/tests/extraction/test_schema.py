from datetime import date
from decimal import Decimal

from receipt_shared.extraction.schema import (
    MAX_LINE_ITEMS,
    GeminiExtraction,
    GeminiLineItem,
    to_domain,
)
from receipt_shared.models.extraction import EXTRACTABLE_FIELDS, ExpenseCategory, PaymentMethod


def _full(**overrides: object) -> GeminiExtraction:
    data: dict[str, object] = {
        "document_type": "receipt",
        "document_number": "R-1",
        "document_date": "2026-03-14",
        "due_date": None,
        "currency": "cad",
        "merchant_name": "  Maple   Leaf\nCafe ",
        "merchant_address": "42 Harbour St",
        "subtotal": 23.2,
        "tax_amount": 3.48,
        "discount_amount": None,
        "total_amount": 26.68,
        "payment_method": "credit_card",
        "line_items": [
            {"description": "Latte", "quantity": 2, "unit_price": 5.25, "total_price": 10.5}
        ],
        "expense_category": "meals",
        "missing_fields": [],
        "extraction_notes": None,
    }
    data.update(overrides)
    return GeminiExtraction.model_validate(data)


def test_money_is_exact_decimal() -> None:
    doc, warnings = to_domain(_full())
    assert doc.subtotal == Decimal("23.2")
    assert doc.tax_amount == Decimal("3.48")
    assert doc.total_amount == Decimal("26.68")  # no binary float artifacts
    assert doc.line_items[0].total_price == Decimal("10.5")
    assert warnings == []


def test_fields_are_normalized() -> None:
    doc, _ = to_domain(_full())
    assert doc.currency == "CAD"
    assert doc.merchant_name == "Maple Leaf Cafe"
    assert doc.document_date == date(2026, 3, 14)
    assert doc.payment_method is PaymentMethod.CREDIT_CARD
    assert doc.expense_category is ExpenseCategory.MEALS


def test_null_amounts_stay_null_not_zero() -> None:
    doc, _ = to_domain(_full(tax_amount=None, discount_amount=None))
    assert doc.tax_amount is None
    assert doc.discount_amount is None


def test_zero_is_preserved_when_printed() -> None:
    doc, _ = to_domain(_full(tax_amount=0.0))
    assert doc.tax_amount == Decimal("0.0")
    assert "tax_amount" not in doc.missing_fields


def test_invalid_date_becomes_null_with_warning() -> None:
    doc, warnings = to_domain(_full(document_date="2026-02-30"))
    assert doc.document_date is None
    assert any("document_date" in w for w in warnings)
    assert "document_date" in doc.missing_fields


def test_invalid_currency_becomes_null_with_warning() -> None:
    doc, warnings = to_domain(_full(currency="dollars"))
    assert doc.currency is None
    assert any("currency" in w for w in warnings)


def test_non_finite_numbers_discarded() -> None:
    doc, warnings = to_domain(_full(total_amount=float("inf")))
    assert doc.total_amount is None
    assert any("total_amount" in w for w in warnings)


def test_missing_fields_reflect_actual_nulls_only() -> None:
    # The model claims merchant_name is missing although it returned one, and invents a name.
    doc, _ = to_domain(_full(missing_fields=["merchant_name", "not_a_field"], due_date=None))
    assert "merchant_name" not in doc.missing_fields
    assert "not_a_field" not in doc.missing_fields
    assert "due_date" in doc.missing_fields
    assert set(doc.missing_fields) <= {*EXTRACTABLE_FIELDS, "line_items"}


def test_all_null_document() -> None:
    doc, warnings = to_domain(GeminiExtraction())
    assert doc.total_amount is None
    assert doc.missing_fields == [*EXTRACTABLE_FIELDS, "line_items"]
    assert warnings == []


def test_empty_line_items_dropped_and_count_capped() -> None:
    items = [
        GeminiLineItem(description=f"item {i}", total_price=1.0) for i in range(MAX_LINE_ITEMS + 5)
    ]
    items.insert(0, GeminiLineItem())
    doc, warnings = to_domain(_full(line_items=items))
    assert all(li.description for li in doc.line_items)
    assert len(doc.line_items) == MAX_LINE_ITEMS - 1  # one empty row inside the cap was dropped
    assert any("truncated" in w for w in warnings)


def test_long_text_is_clipped() -> None:
    doc, _ = to_domain(_full(extraction_notes="x" * 10_000, merchant_name="m" * 900))
    assert len(doc.extraction_notes or "") == 2000
    assert len(doc.merchant_name or "") == 500


def test_other_document_type_is_kept_for_validation() -> None:
    doc, _ = to_domain(_full(document_type="other"))
    assert doc.document_type == "other"
