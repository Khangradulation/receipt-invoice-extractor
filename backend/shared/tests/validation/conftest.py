from collections.abc import Callable
from datetime import date
from decimal import Decimal
from typing import Any

import pytest

from receipt_shared.models.extraction import (
    ExpenseCategory,
    ExtractedDocument,
    LineItem,
    PaymentMethod,
)
from receipt_shared.validation import ValidationConfig

TODAY = date(2026, 11, 9)
D = Decimal


def _base() -> dict[str, Any]:
    return {
        "document_type": "receipt",
        "document_number": "R-10482",
        "document_date": date(2026, 3, 14),
        "currency": "CAD",
        "merchant_name": "Maple Leaf Cafe",
        "merchant_address": "42 Harbour Street, Halifax",
        "subtotal": D("23.20"),
        "tax_amount": D("3.48"),
        "total_amount": D("26.68"),
        "payment_method": PaymentMethod.CREDIT_CARD,
        "expense_category": ExpenseCategory.MEALS,
        "line_items": [
            LineItem(
                description="Latte", quantity=D("2"), unit_price=D("5.25"), total_price=D("10.50")
            ),
            LineItem(
                description="Muffin", quantity=D("1"), unit_price=D("3.75"), total_price=D("3.75")
            ),
            LineItem(
                description="Sandwich", quantity=D("1"), unit_price=D("8.95"), total_price=D("8.95")
            ),
        ],
    }


DocFactory = Callable[..., ExtractedDocument]


@pytest.fixture
def make_doc() -> DocFactory:
    """A fully valid receipt; keyword overrides break it in exactly one way."""

    def factory(**overrides: Any) -> ExtractedDocument:
        return ExtractedDocument(**{**_base(), **overrides})

    return factory


@pytest.fixture
def cfg() -> ValidationConfig:
    return ValidationConfig(
        money_tolerance=D("0.02"),
        line_item_tolerance=D("0.05"),
        supported_currencies=frozenset({"USD", "CAD", "EUR", "GBP", "JPY", "KWD"}),
        future_date_tolerance_days=1,
        max_document_age_days=3650,
        max_reasonable_amount=D("1000000"),
    )
