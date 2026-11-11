"""Fictional merchants, items and locales for the synthetic benchmark (no real businesses)."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class Locale:
    country: str
    currency: str
    symbol: str  # printed before amounts ("$" or a 3-letter code + space)
    city_lines: tuple[str, ...]
    date_style: str  # iso | us | eu | long
    taxes: tuple[tuple[str, Decimal], ...]  # printed tax lines and rates
    tax_inclusive: bool = False  # VAT already included in item prices
    decimals: int = 2


LOCALES: dict[str, Locale] = {
    "US": Locale(
        "USA",
        "USD",
        "$",
        ("Portland, OR 97201, USA", "Austin, TX 78701, USA"),
        "us",
        (("Sales tax", Decimal("0.0825")),),
    ),
    "CA_NS": Locale(
        "Canada", "CAD", "$", ("Halifax, NS B3J 1A1, Canada",), "iso", (("HST", Decimal("0.15")),)
    ),
    "CA_BC": Locale(
        "Canada",
        "CAD",
        "$",
        ("Vancouver, BC V6B 1A1, Canada",),
        "long",
        (("GST", Decimal("0.05")), ("PST", Decimal("0.07"))),
    ),
    "DE": Locale(
        "Germany",
        "EUR",
        "EUR ",
        ("10969 Berlin, Germany", "80331 Munich, Germany"),
        "eu",
        (("VAT", Decimal("0.19")),),
        tax_inclusive=True,
    ),
    "UK": Locale(
        "United Kingdom",
        "GBP",
        "GBP ",
        ("Leeds LS1 4AP, United Kingdom",),
        "eu",
        (("VAT", Decimal("0.20")),),
        tax_inclusive=True,
    ),
    "AU": Locale(
        "Australia", "AUD", "$", ("Sydney NSW 2000, Australia",), "eu", (("GST", Decimal("0.10")),)
    ),
    "IN": Locale(
        "India",
        "INR",
        "INR ",
        ("Pune 411001, India",),
        "eu",
        (("CGST", Decimal("0.09")), ("SGST", Decimal("0.09"))),
    ),
    "JP": Locale(
        "Japan",
        "JPY",
        "JPY ",
        ("Chiyoda, Tokyo 100-0001, Japan",),
        "iso",
        (("Consumption tax", Decimal("0.10")),),
        decimals=0,
    ),
    "PK": Locale(
        "Pakistan",
        "PKR",
        "PKR ",
        ("Gulberg, Lahore 54660, Pakistan",),
        "eu",
        (("GST", Decimal("0.18")),),
    ),
}

STREETS = (
    "Harbour Street",
    "Mill Road",
    "Elm Avenue",
    "Water Street",
    "King Street",
    "Station Road",
    "Market Lane",
    "Lindenstrasse",
    "Main Street",
    "Park Road",
)

# category -> (merchant names, (item name, low price, high price) ...)
CATEGORIES: dict[str, tuple[tuple[str, ...], tuple[tuple[str, int, int], ...]]] = {
    "meals": (
        ("Maple Leaf Cafe", "Blue Door Bistro", "Golden Spoon Diner", "Harbour Grill"),
        (
            ("Latte", 4, 7),
            ("Breakfast sandwich", 7, 12),
            ("Soup of the day", 6, 10),
            ("Club sandwich", 11, 16),
            ("Iced tea", 3, 5),
            ("Blueberry muffin", 3, 5),
        ),
    ),
    "groceries": (
        ("Corner Grocery Market", "Green Basket Foods", "Daily Fresh Mart"),
        (
            ("Bananas 1kg", 1, 3),
            ("Whole milk 2L", 2, 4),
            ("Sourdough loaf", 3, 6),
            ("Free-range eggs 12", 4, 7),
            ("Cheddar 400g", 5, 9),
            ("Olive oil 1L", 8, 14),
        ),
    ),
    "office_supplies": (
        ("Paperclip Office Supply", "Riverside Stationers"),
        (
            ("Printer paper A4 ream", 6, 10),
            ("Gel pens 10-pack", 5, 9),
            ("Stapler", 9, 18),
            ("Toner cartridge", 45, 90),
            ("Desk organiser", 15, 30),
        ),
    ),
    "equipment": (
        ("Riverside Hardware Supply", "Northgate Tools"),
        (
            ("Cordless drill bit set", 20, 40),
            ("Wood screws 2in box", 5, 9),
            ("Painter's tape", 3, 6),
            ("Extension cord 5m", 12, 25),
            ("Safety gloves", 6, 12),
        ),
    ),
    "fuel": (
        ("Highway 9 Fuel Stop", "Sunrise Petroleum"),
        (("Unleaded fuel", 40, 90), ("Car wash", 8, 15), ("Windshield fluid", 4, 8)),
    ),
    "lodging": (
        ("Seaview Inn", "The Granite Hotel"),
        (("Room night - standard king", 120, 260), ("City tax", 3, 8), ("Breakfast", 15, 25)),
    ),
    "transportation": (
        ("Metro Cab Co", "Swift Airport Shuttle"),
        (("Fare", 18, 60), ("Booking fee", 2, 5), ("Airport surcharge", 5, 10)),
    ),
    "software": (
        ("Cloudnest Software Ltd", "Pixelforge Apps Inc"),
        (
            ("Team plan - monthly", 30, 120),
            ("Additional seat", 8, 20),
            ("Storage add-on 100GB", 5, 15),
        ),
    ),
    "professional_services": (
        ("Northwind Analytics", "Bright Ledger Consulting", "Atlas Design Studio"),
        (
            ("Data pipeline consulting", 90, 160),
            ("Dashboard design", 80, 140),
            ("Workshop facilitation", 400, 900),
            ("Monthly retainer", 1200, 3000),
        ),
    ),
    "telecommunications": (
        ("Signal Wave Mobile", "Fibrelink Broadband"),
        (
            ("Mobile plan - monthly", 30, 70),
            ("Fibre internet 500Mbps", 50, 90),
            ("Device installment", 20, 45),
        ),
    ),
    "shipping": (
        ("Parcel Express Courier", "Swiftbox Logistics"),
        (("Next-day parcel", 12, 30), ("Insurance cover", 2, 6), ("Pallet freight", 80, 200)),
    ),
    "healthcare": (
        ("Wellspring Pharmacy",),
        (("Pain relief tablets", 4, 9), ("Vitamin D", 8, 15), ("First aid kit", 15, 30)),
    ),
}

INVOICE_CATEGORIES = (
    "professional_services",
    "software",
    "telecommunications",
    "shipping",
    "office_supplies",
)
RECEIPT_CATEGORIES = tuple(c for c in CATEGORIES if c not in ("professional_services",))

BUYERS = (
    "Example Buyer Ltd.",
    "Fictional Holdings Inc.",
    "Sample Trading Co.",
    "Demo Ventures LLC",
)
