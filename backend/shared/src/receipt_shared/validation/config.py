"""Validation configuration, derived from ``Settings`` so every threshold is configurable."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from receipt_shared.config import Settings

REQUIRED_FIELDS: tuple[str, ...] = (
    "merchant_name",
    "document_date",
    "total_amount",
    "currency",
    "document_type",
)

# Missing these is reported as a warning but never blocks acceptance.
OPTIONAL_FIELDS: tuple[str, ...] = (
    "document_number",
    "merchant_address",
    "subtotal",
    "tax_amount",
    "payment_method",
    "expense_category",
)

VALID_DOCUMENT_TYPES: frozenset[str] = frozenset({"receipt", "invoice"})

# ISO 4217 minor units for currencies that do not use 2 decimals. Default is 2.
_MINOR_UNITS: dict[str, int] = {
    "JPY": 0, "KRW": 0, "VND": 0, "CLP": 0, "ISK": 0, "HUF": 2, "TWD": 2,
    "BHD": 3, "KWD": 3, "OMR": 3, "JOD": 3, "TND": 3, "LYD": 3, "IQD": 3,
}  # fmt: skip


def minor_unit(currency: str | None) -> Decimal:
    """Smallest unit of the currency, e.g. 0.01 for USD, 1 for JPY, 0.001 for KWD."""
    digits = _MINOR_UNITS.get((currency or "").upper(), 2)
    return Decimal(1).scaleb(-digits)


@dataclass(frozen=True)
class ValidationConfig:
    money_tolerance: Decimal = Decimal("0.02")
    line_item_tolerance: Decimal = Decimal("0.05")
    supported_currencies: frozenset[str] = field(
        default_factory=lambda: frozenset({"USD", "CAD", "EUR", "GBP"})
    )
    future_date_tolerance_days: int = 1
    max_document_age_days: int = 3650
    max_reasonable_amount: Decimal = Decimal("1000000")

    @classmethod
    def from_settings(cls, settings: Settings) -> ValidationConfig:
        return cls(
            money_tolerance=settings.money_tolerance,
            line_item_tolerance=settings.line_item_tolerance,
            supported_currencies=frozenset(c.upper() for c in settings.supported_currencies),
            future_date_tolerance_days=settings.future_date_tolerance_days,
            max_document_age_days=settings.max_document_age_days,
            max_reasonable_amount=settings.max_reasonable_amount,
        )

    def money_tol(self, currency: str | None) -> Decimal:
        """Tolerance for totals: the configured value, but never below one minor unit."""
        return max(self.money_tolerance, minor_unit(currency))

    def line_tol(self, currency: str | None) -> Decimal:
        return max(self.line_item_tolerance, minor_unit(currency))
