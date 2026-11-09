"""Domain model for data extracted from a receipt or invoice.

These models are deliberately independent of Gemini: the validation engine, API, worker and
evaluation suite all consume them. Every extracted field is optional — a value that could not be
read is ``None``, never a guessed default (in particular, never ``0``).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class ExpenseCategory(StrEnum):
    MEALS = "meals"
    GROCERIES = "groceries"
    TRAVEL = "travel"
    LODGING = "lodging"
    TRANSPORTATION = "transportation"
    FUEL = "fuel"
    OFFICE_SUPPLIES = "office_supplies"
    SOFTWARE = "software"
    EQUIPMENT = "equipment"
    UTILITIES = "utilities"
    TELECOMMUNICATIONS = "telecommunications"
    PROFESSIONAL_SERVICES = "professional_services"
    RENT = "rent"
    INSURANCE = "insurance"
    SHIPPING = "shipping"
    ENTERTAINMENT = "entertainment"
    HEALTHCARE = "healthcare"
    OTHER = "other"


class PaymentMethod(StrEnum):
    CASH = "cash"
    CREDIT_CARD = "credit_card"
    DEBIT_CARD = "debit_card"
    BANK_TRANSFER = "bank_transfer"
    CHECK = "check"
    MOBILE_PAYMENT = "mobile_payment"
    OTHER = "other"


class LineItem(BaseModel):
    model_config = ConfigDict(frozen=True)

    description: str | None = None
    quantity: Decimal | None = None
    unit_price: Decimal | None = None
    total_price: Decimal | None = None


class ExtractedDocument(BaseModel):
    """Structured fields read from one document."""

    # Document information
    document_type: str | None = Field(
        default=None, description="'receipt', 'invoice', or 'other' as classified by the model"
    )
    document_number: str | None = None
    document_date: date | None = None
    due_date: date | None = None
    currency: str | None = Field(default=None, description="ISO 4217 code, upper case")
    merchant_name: str | None = None
    merchant_address: str | None = None

    # Financial information
    subtotal: Decimal | None = None
    tax_amount: Decimal | None = None
    discount_amount: Decimal | None = None
    total_amount: Decimal | None = None

    # Payment
    payment_method: PaymentMethod | None = None

    # Line items
    line_items: list[LineItem] = Field(default_factory=list)

    # Classification
    expense_category: ExpenseCategory | None = None

    # Additional information
    missing_fields: list[str] = Field(default_factory=list)
    extraction_notes: str | None = None


# Top-level scalar fields that can be reported as missing.
EXTRACTABLE_FIELDS: tuple[str, ...] = (
    "document_type",
    "document_number",
    "document_date",
    "due_date",
    "currency",
    "merchant_name",
    "merchant_address",
    "subtotal",
    "tax_amount",
    "discount_amount",
    "total_amount",
    "payment_method",
    "expense_category",
)


class ExtractionMetadata(BaseModel):
    """How an extraction was produced — stored with every result for traceability."""

    model: str = Field(description="Configured model name, e.g. gemini-2.5-flash")
    model_version: str | None = Field(
        default=None, description="Exact model version reported by the API"
    )
    prompt_version: str
    location: str
    latency_ms: float = Field(description="Wall-clock time across all attempts")
    attempts: int
    prompt_tokens: int | None = None
    output_tokens: int | None = None
    thoughts_tokens: int | None = None
    total_tokens: int | None = None
    finish_reason: str | None = None


class ExtractionResult(BaseModel):
    document: ExtractedDocument
    metadata: ExtractionMetadata
    warnings: list[str] = Field(
        default_factory=list,
        description="Normalization issues, e.g. a date the model returned that is not a real date",
    )
