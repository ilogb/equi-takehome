"""Parse numbers as printed in fund documents into Decimals; snap period ends."""

import calendar
import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Literal

from app.models import PeriodKind

Unit = Literal["fraction", "currency", "number"]
UnitHint = Literal["percent", "fraction", "currency", "number"]

_PLACEHOLDERS = {"", "-", "–", "—", "n/a", "n/m"}
_CURRENCY_SYMBOLS = {"$": "USD", "€": "EUR", "£": "GBP"}
_ISO_CODES = "USD|EUR|GBP|CHF|JPY|CAD|AUD|NZD|HKD|SGD|SEK|NOK|DKK|CNY"
_ISO_PREFIX = re.compile(rf"^(-\s*)?({_ISO_CODES})\s+", re.IGNORECASE)
_ISO_SUFFIX = re.compile(rf"\s+({_ISO_CODES})$", re.IGNORECASE)
_MULTIPLIERS = {"m": Decimal(10) ** 6, "bn": Decimal(10) ** 9}
_NUMBER = re.compile(
    r"""^(?P<neg>-)?\s*(?P<cur>[$€£])?\s*(?P<neg2>-)?\s*
        (?P<num>\d[\d,]*(?:\.\d+)?|\.\d+)\s*
        (?P<suffix>%|bps|bn|m)?$""",
    re.VERBOSE | re.IGNORECASE,
)


@dataclass(frozen=True)
class ParsedValue:
    value: Decimal
    unit: Unit
    currency: str | None


def parse_value(text: str, unit_hint: UnitHint | None) -> ParsedValue | None:
    s = text.strip().rstrip("*").rstrip().replace("−", "-").replace("+", "", 1)
    if s.lower() in _PLACEHOLDERS:
        return None
    negative = False
    if s.startswith("(") and s.endswith(")"):
        negative = True
        s = s[1:-1].strip()
    iso: str | None = None
    if pre := _ISO_PREFIX.match(s):
        iso = pre[2].upper()
        s = ("-" if pre[1] else "") + s[pre.end():]
    elif suf := _ISO_SUFFIX.search(s):
        iso = suf[1].upper()
        s = s[: suf.start()]
    m = _NUMBER.match(s)
    if not m:
        return None
    try:
        value = Decimal(m["num"].replace(",", ""))
    except InvalidOperation:
        return None
    negative = negative or bool(m["neg"] or m["neg2"])
    suffix = (m["suffix"] or "").lower()
    currency = _CURRENCY_SYMBOLS.get(m["cur"]) if m["cur"] else iso

    unit: Unit
    if suffix == "%" or (unit_hint == "percent" and not suffix):
        value, unit = value / 100, "fraction"
    elif suffix == "bps":
        value, unit = value / 10000, "fraction"
    elif suffix in _MULTIPLIERS:
        value, unit = value * _MULTIPLIERS[suffix], "currency"
    elif currency or unit_hint == "currency":
        unit = "currency"
    elif unit_hint == "fraction":
        unit = "fraction"
    else:
        unit = "number"
    if currency:
        unit = "currency"
    return ParsedValue(-value if negative else value, unit, currency)


def snap_period_end(d: date, kind: PeriodKind) -> date:
    if kind in (PeriodKind.month, PeriodKind.qtd, PeriodKind.ytd, PeriodKind.y1):
        return d.replace(day=calendar.monthrange(d.year, d.month)[1])
    return d
