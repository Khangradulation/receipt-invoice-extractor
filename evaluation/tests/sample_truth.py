"""Shared ground-truth fixture for the scoring and aggregation tests."""

from typing import Any


def item(desc: str, total: str, qty: str | None = None, unit: str | None = None) -> dict[str, Any]:
    return {"description": desc, "quantity": qty, "unit_price": unit, "total_price": total}


TRUTH = {
    "document_type": "receipt",
    "document_number": "R-1",
    "document_date": "2026-03-14",
    "due_date": None,
    "currency": "CAD",
    "merchant_name": "Maple Leaf Cafe",
    "merchant_address": "42 Harbour St, Halifax",
    "subtotal": "23.20",
    "tax_amount": "3.48",
    "discount_amount": None,
    "total_amount": "26.68",
    "payment_method": "credit_card",
    "expense_category": "meals",
    "line_items": [item("Latte", "10.50", "2", "5.25"), item("Club sandwich", "12.70")],
}
