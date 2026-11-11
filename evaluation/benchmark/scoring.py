"""Compare an extraction with ground truth.

Every field produces one of:
  correct        values match (or both are null)
  wrong          both present but different
  missed         printed on the document, extracted as null
  hallucinated   not printed (truth null) but a value was returned

Money is compared as Decimal within a tolerance (default: one minor unit of the currency); text
fields ignore case, punctuation and spacing; document numbers ignore separators.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from difflib import SequenceMatcher
from typing import Any

MONEY_FIELDS = ("subtotal", "tax_amount", "discount_amount", "total_amount")
FIELD_KINDS: dict[str, str] = {
    "document_type": "exact",
    "document_number": "id",
    "document_date": "exact",
    "due_date": "exact",
    "currency": "upper",
    "merchant_name": "text",
    "merchant_address": "text",
    "subtotal": "money",
    "tax_amount": "money",
    "discount_amount": "money",
    "total_amount": "money",
    "payment_method": "exact",
    "expense_category": "exact",
}
REQUIRED_FIELDS = ("merchant_name", "document_date", "total_amount", "currency", "document_type")
# "Core" = everything objectively printed. Address, payment method and category are reported
# separately because they are partly interpretive (formatting, card brand, category choice).
CORE_FIELDS = (
    *REQUIRED_FIELDS,
    "document_number",
    "subtotal",
    "tax_amount",
    "discount_amount",
    "due_date",
)
TEXT_SIMILARITY = 0.92
ITEM_DESCRIPTION_SIMILARITY = 0.8

_NON_ALNUM = re.compile(r"[^0-9a-z]+")
_MINOR_UNITS = {"JPY": 0, "KRW": 0}


def norm_text(value: str) -> str:
    ascii_value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    ascii_value = ascii_value.replace("&", " and ")  # "Books & Coffee" == "Books and Coffee"
    return " ".join(_NON_ALNUM.sub(" ", ascii_value.casefold()).split())


def similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, norm_text(a), norm_text(b)).ratio()


def to_decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def money_tolerance(currency: str | None, extra: Decimal = Decimal("0")) -> Decimal:
    unit = Decimal(1).scaleb(-_MINOR_UNITS.get((currency or "").upper(), 2))
    return max(unit, extra)


def _blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def values_match(kind: str, truth: Any, pred: Any, *, tolerance: Decimal) -> bool:
    if kind == "money":
        t, p = to_decimal(truth), to_decimal(pred)
        return t is not None and p is not None and abs(t - p) <= tolerance
    if kind == "text":
        return (
            norm_text(str(truth)) == norm_text(str(pred))
            or similarity(str(truth), str(pred)) >= TEXT_SIMILARITY
        )
    if kind == "id":
        return _NON_ALNUM.sub("", str(truth).casefold()) == _NON_ALNUM.sub("", str(pred).casefold())
    if kind == "upper":
        return str(truth).strip().upper() == str(pred).strip().upper()
    return str(truth).strip() == str(pred).strip()


def compare_field(name: str, truth: Any, pred: Any, *, tolerance: Decimal) -> str:
    if _blank(truth) and _blank(pred):
        return "correct"
    if _blank(truth):
        return "hallucinated"
    if _blank(pred):
        return "missed"
    return (
        "correct" if values_match(FIELD_KINDS[name], truth, pred, tolerance=tolerance) else "wrong"
    )


@dataclass
class LineItemScore:
    truth_count: int
    predicted_count: int
    matched: int
    quantity_correct: int = 0
    quantity_compared: int = 0
    unit_price_correct: int = 0
    unit_price_compared: int = 0

    @property
    def precision(self) -> float:
        return (
            self.matched / self.predicted_count
            if self.predicted_count
            else (1.0 if not self.truth_count else 0.0)
        )

    @property
    def recall(self) -> float:
        return self.matched / self.truth_count if self.truth_count else 1.0

    @property
    def exact(self) -> bool:
        """Every printed line found, nothing extra."""
        return self.matched == self.truth_count == self.predicted_count


def score_line_items(
    truth: list[dict[str, Any]], pred: list[dict[str, Any]], *, tolerance: Decimal
) -> LineItemScore:
    """Greedy one-to-one matching on description similarity + line total within tolerance."""
    score = LineItemScore(truth_count=len(truth), predicted_count=len(pred), matched=0)
    unused = list(range(len(pred)))
    for t in truth:
        best, best_sim = None, 0.0
        for j in unused:
            p = pred[j]
            sim = similarity(str(t.get("description") or ""), str(p.get("description") or ""))
            amounts_ok = values_match(
                "money", t.get("total_price"), p.get("total_price"), tolerance=tolerance
            )
            if amounts_ok and sim >= ITEM_DESCRIPTION_SIMILARITY and sim > best_sim:
                best, best_sim = j, sim
        if best is None:
            continue
        unused.remove(best)
        score.matched += 1
        p = pred[best]
        if not _blank(t.get("quantity")):
            score.quantity_compared += 1
            score.quantity_correct += values_match(
                "money", t["quantity"], p.get("quantity"), tolerance=Decimal("0.001")
            )
        if not _blank(t.get("unit_price")):
            score.unit_price_compared += 1
            score.unit_price_correct += values_match(
                "money", t["unit_price"], p.get("unit_price"), tolerance=tolerance
            )
    return score


@dataclass
class DocumentScore:
    name: str
    fields: dict[str, str]
    line_items: LineItemScore
    differences: dict[str, dict[str, Any]] = field(default_factory=dict)

    @property
    def fields_compared(self) -> int:
        return len(self.fields)

    @property
    def fields_correct(self) -> int:
        return sum(v == "correct" for v in self.fields.values())

    @property
    def required_correct(self) -> bool:
        return all(self.fields[f] == "correct" for f in REQUIRED_FIELDS)

    @property
    def core_correct(self) -> bool:
        return all(self.fields[f] == "correct" for f in CORE_FIELDS)

    @property
    def fully_correct(self) -> bool:
        return self.core_correct and self.line_items.exact


def score_document(
    name: str,
    truth: dict[str, Any],
    pred: dict[str, Any],
    *,
    money_tolerance_extra: Decimal = Decimal("0"),
) -> DocumentScore:
    tolerance = money_tolerance(truth.get("currency"), money_tolerance_extra)
    fields: dict[str, str] = {}
    diffs: dict[str, dict[str, Any]] = {}
    for name_ in FIELD_KINDS:
        outcome = compare_field(name_, truth.get(name_), pred.get(name_), tolerance=tolerance)
        fields[name_] = outcome
        if outcome != "correct":
            diffs[name_] = {
                "truth": truth.get(name_),
                "predicted": pred.get(name_),
                "outcome": outcome,
            }
    items = score_line_items(
        truth.get("line_items") or [], pred.get("line_items") or [], tolerance=tolerance
    )
    return DocumentScore(name=name, fields=fields, line_items=items, differences=diffs)
