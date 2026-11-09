"""Individual validation rules.

Each rule takes the extracted document (plus config / context) and returns a list of issues.
Rules never modify the document and never assume a missing value is zero.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, timedelta
from decimal import Decimal

from receipt_shared.models.extraction import ExtractedDocument
from receipt_shared.models.validation import Severity, ValidationCode, ValidationIssue
from receipt_shared.validation.config import (
    OPTIONAL_FIELDS,
    REQUIRED_FIELDS,
    VALID_DOCUMENT_TYPES,
    ValidationConfig,
    minor_unit,
)

Rule = Callable[[ExtractedDocument, ValidationConfig, date], list[ValidationIssue]]

_ZERO = Decimal("0")
_LABELS = {
    "merchant_name": "Merchant name",
    "document_date": "Document date",
    "total_amount": "Total amount",
    "currency": "Currency",
    "document_type": "Document type",
    "document_number": "Document number",
    "merchant_address": "Merchant address",
    "subtotal": "Subtotal",
    "tax_amount": "Tax amount",
    "discount_amount": "Discount",
    "payment_method": "Payment method",
    "expense_category": "Expense category",
    "due_date": "Due date",
    "line_items": "Line items",
}


def _error(code: ValidationCode, message: str, *fields: str) -> ValidationIssue:
    return ValidationIssue(code=code, severity=Severity.ERROR, message=message, fields=list(fields))


def _warning(code: ValidationCode, message: str, *fields: str) -> ValidationIssue:
    return ValidationIssue(
        code=code, severity=Severity.WARNING, message=message, fields=list(fields)
    )


def _fmt(value: Decimal, currency: str | None) -> str:
    places = minor_unit(currency)
    text = f"{value.quantize(places):,}" if value == value.quantize(places) else f"{value:,}"
    return f"{text} {currency}".strip() if currency else text


# --- Fields ------------------------------------------------------------------------------------
def required_fields(
    doc: ExtractedDocument, cfg: ValidationConfig, today: date
) -> list[ValidationIssue]:
    issues = []
    for name in REQUIRED_FIELDS:
        value = getattr(doc, name)
        if value is None or (isinstance(value, str) and not value.strip()):
            issues.append(
                _error(
                    ValidationCode.MISSING_REQUIRED_FIELD,
                    f"{_LABELS[name]} is missing or could not be read.",
                    name,
                )
            )
    return issues


def optional_fields(
    doc: ExtractedDocument, cfg: ValidationConfig, today: date
) -> list[ValidationIssue]:
    issues = [
        _warning(
            ValidationCode.MISSING_OPTIONAL_FIELD,
            f"{_LABELS[name]} was not found on the document.",
            name,
        )
        for name in OPTIONAL_FIELDS
        if getattr(doc, name) is None
    ]
    if not doc.line_items:
        issues.append(
            _warning(
                ValidationCode.MISSING_OPTIONAL_FIELD,
                "No line items were found on the document.",
                "line_items",
            )
        )
    if doc.document_type == "invoice" and doc.due_date is None:
        issues.append(
            _warning(ValidationCode.MISSING_OPTIONAL_FIELD, "Invoice has no due date.", "due_date")
        )
    return issues


def document_type(
    doc: ExtractedDocument, cfg: ValidationConfig, today: date
) -> list[ValidationIssue]:
    if doc.document_type is None:
        return []  # reported by required_fields
    if doc.document_type not in VALID_DOCUMENT_TYPES:
        return [
            _error(
                ValidationCode.INVALID_DOCUMENT_TYPE,
                f"Document type '{doc.document_type}' is not supported; expected a receipt or an "
                "invoice.",
                "document_type",
            )
        ]
    return []


def invoice_number(
    doc: ExtractedDocument, cfg: ValidationConfig, today: date
) -> list[ValidationIssue]:
    if doc.document_type == "invoice" and not doc.document_number:
        return [
            _warning(
                ValidationCode.INVOICE_WITHOUT_NUMBER,
                "Invoice has no invoice number; duplicate detection is less reliable.",
                "document_number",
            )
        ]
    return []


def currency(doc: ExtractedDocument, cfg: ValidationConfig, today: date) -> list[ValidationIssue]:
    if doc.currency is None:
        return []  # reported by required_fields
    if doc.currency.upper() not in cfg.supported_currencies:
        return [
            _error(
                ValidationCode.UNSUPPORTED_CURRENCY,
                f"Currency '{doc.currency}' is not supported. Supported: "
                f"{', '.join(sorted(cfg.supported_currencies))}.",
                "currency",
            )
        ]
    return []


# --- Dates -------------------------------------------------------------------------------------
def dates(doc: ExtractedDocument, cfg: ValidationConfig, today: date) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    if doc.document_date is not None:
        if doc.document_date > today + timedelta(days=cfg.future_date_tolerance_days):
            issues.append(
                _error(
                    ValidationCode.DATE_IN_FUTURE,
                    f"Document date {doc.document_date.isoformat()} is in the future.",
                    "document_date",
                )
            )
        elif doc.document_date < today - timedelta(days=cfg.max_document_age_days):
            issues.append(
                _warning(
                    ValidationCode.DATE_TOO_OLD,
                    f"Document date {doc.document_date.isoformat()} is unusually old; please "
                    "confirm it was read correctly.",
                    "document_date",
                )
            )
    if (
        doc.due_date is not None
        and doc.document_date is not None
        and doc.due_date < doc.document_date
    ):
        issues.append(
            _warning(
                ValidationCode.DUE_DATE_BEFORE_DOCUMENT_DATE,
                f"Due date {doc.due_date.isoformat()} is before the document date "
                f"{doc.document_date.isoformat()}.",
                "due_date",
                "document_date",
            )
        )
    return issues


# --- Amounts -----------------------------------------------------------------------------------
_AMOUNT_FIELDS = ("subtotal", "tax_amount", "total_amount")


def amounts(doc: ExtractedDocument, cfg: ValidationConfig, today: date) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for name in _AMOUNT_FIELDS:
        value: Decimal | None = getattr(doc, name)
        if value is None:
            continue
        if value < _ZERO:
            issues.append(
                _error(
                    ValidationCode.NEGATIVE_AMOUNT,
                    f"{_LABELS[name]} must not be negative (read as {_fmt(value, doc.currency)}).",
                    name,
                )
            )
        if abs(value) > cfg.max_reasonable_amount:
            issues.append(
                _warning(
                    ValidationCode.AMOUNT_TOO_LARGE,
                    f"{_LABELS[name]} of {_fmt(value, doc.currency)} is unusually large; please "
                    "confirm it was read correctly.",
                    name,
                )
            )
    for name in (*_AMOUNT_FIELDS, "discount_amount"):
        value = getattr(doc, name)
        if value is not None and doc.currency and value != value.quantize(minor_unit(doc.currency)):
            issues.append(
                _warning(
                    ValidationCode.TOO_MANY_DECIMALS,
                    f"{_LABELS[name]} has more decimal places than {doc.currency} uses.",
                    name,
                )
            )
    if doc.discount_amount is not None and doc.discount_amount < _ZERO:
        issues.append(
            _warning(
                ValidationCode.NEGATIVE_DISCOUNT,
                "Discount was read as a negative number; it is treated as a reduction of "
                f"{_fmt(abs(doc.discount_amount), doc.currency)}.",
                "discount_amount",
            )
        )
    if doc.total_amount is not None and doc.total_amount == _ZERO:
        issues.append(_warning(ValidationCode.ZERO_TOTAL, "Total amount is zero.", "total_amount"))
    return issues


# --- Arithmetic --------------------------------------------------------------------------------
def totals(doc: ExtractedDocument, cfg: ValidationConfig, today: date) -> list[ValidationIssue]:
    """Check subtotal, discount and tax against the total.

    Accepted layouts (within tolerance):
      1. total = subtotal - discount + tax           (standard)
      2. total = subtotal - discount                 (tax included in prices, or no tax)
      3. total = subtotal + tax                      (discount already applied to the subtotal)
    """
    total, subtotal, tax = doc.total_amount, doc.subtotal, doc.tax_amount
    if total is None:
        return []  # reported by required_fields
    if subtotal is None:
        return [
            _warning(
                ValidationCode.TOTALS_NOT_VERIFIABLE,
                "No subtotal was found, so the total could not be cross-checked.",
                "subtotal",
                "total_amount",
            )
        ]

    cur = doc.currency
    tol = cfg.money_tol(cur)
    discount = abs(doc.discount_amount) if doc.discount_amount is not None else _ZERO

    def close(expected: Decimal) -> bool:
        return abs(total - expected) <= tol

    if tax is not None and close(subtotal - discount + tax):
        return []
    if close(subtotal - discount):
        if tax is not None and tax > _ZERO:
            return [
                _warning(
                    ValidationCode.TAX_INCLUDED_IN_SUBTOTAL,
                    "The tax appears to be included in the subtotal (subtotal "
                    f"{'- discount ' if discount else ''}= total).",
                    "tax_amount",
                )
            ]
        return []
    if discount and tax is not None and close(subtotal + tax):
        return []  # discount already reflected in the subtotal

    fields = ["subtotal", "total_amount"]
    parts = [f"subtotal {_fmt(subtotal, cur)}"]
    expected = subtotal - discount
    if discount:
        parts.append(f"- discount {_fmt(discount, cur)}")
        fields.append("discount_amount")
    if tax is not None:
        parts.append(f"+ tax {_fmt(tax, cur)}")
        expected += tax
        fields.append("tax_amount")
    message = (
        f"Amounts do not add up: {' '.join(parts)} = {_fmt(expected, cur)}, but the total is "
        f"{_fmt(total, cur)} (difference {_fmt(total - expected, cur)})."
    )
    if tax is None:
        message += " No tax amount was found; the difference may be unread tax, a tip or a fee."
    return [_error(ValidationCode.TOTAL_MISMATCH, message, *fields)]


def line_items(doc: ExtractedDocument, cfg: ValidationConfig, today: date) -> list[ValidationIssue]:
    """Check each line's quantity x unit price, and the sum of lines against the totals."""
    if not doc.line_items:
        return []
    cur = doc.currency
    tol = cfg.line_tol(cur)
    issues: list[ValidationIssue] = []

    bad_lines = [
        str(i + 1)
        for i, li in enumerate(doc.line_items)
        if li.quantity is not None
        and li.unit_price is not None
        and li.total_price is not None
        and abs(li.quantity * li.unit_price - li.total_price) > tol
    ]
    if bad_lines:
        issues.append(
            _warning(
                ValidationCode.LINE_ITEM_ARITHMETIC,
                f"Quantity x unit price does not match the line total on line(s) "
                f"{', '.join(bad_lines)}.",
                "line_items",
            )
        )

    if any(li.total_price is None for li in doc.line_items):
        return issues  # cannot sum reliably
    line_sum = sum((li.total_price for li in doc.line_items if li.total_price is not None), _ZERO)

    discount = abs(doc.discount_amount) if doc.discount_amount is not None else _ZERO
    targets: list[Decimal] = []
    if doc.subtotal is not None:
        targets += [doc.subtotal, doc.subtotal - discount]
    if doc.total_amount is not None:
        targets.append(doc.total_amount)
        if doc.tax_amount is not None:
            targets += [
                doc.total_amount - doc.tax_amount,
                doc.total_amount - doc.tax_amount + discount,
            ]
    if not targets:
        return issues
    if not any(abs(line_sum - t) <= tol for t in targets):
        reference = (
            f"subtotal {_fmt(doc.subtotal, cur)}"
            if doc.subtotal is not None
            else f"total {_fmt(doc.total_amount, cur)}"  # type: ignore[arg-type]
        )
        issues.append(
            _warning(
                ValidationCode.LINE_ITEMS_MISMATCH,
                f"Line items add up to {_fmt(line_sum, cur)}, which does not match the "
                f"{reference}. Some items may be missing or misread.",
                "line_items",
            )
        )
    return issues


ALL_RULES: tuple[Rule, ...] = (
    required_fields,
    document_type,
    currency,
    dates,
    amounts,
    totals,
    line_items,
    invoice_number,
    optional_fields,
)
