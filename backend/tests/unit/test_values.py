from datetime import date
from decimal import Decimal

import pytest

from app.models import PeriodKind
from app.values import ParsedValue, parse_value, snap_period_end

D = Decimal


@pytest.mark.parametrize(
    ("text", "hint", "expected"),
    [
        ("1.23%", None, ParsedValue(D("0.0123"), "fraction", None)),
        ("(0.84%)", None, ParsedValue(D("-0.0084"), "fraction", None)),
        ("−0.45%", None, ParsedValue(D("-0.0045"), "fraction", None)),
        ("+13.6", "percent", ParsedValue(D("0.136"), "fraction", None)),
        ("12 bps", None, ParsedValue(D("0.0012"), "fraction", None)),
        ("$612m", None, ParsedValue(D("612000000"), "currency", "USD")),
        ("€5.8bn", None, ParsedValue(D("5800000000"), "currency", "EUR")),
        ("$24,963,108.45", None, ParsedValue(D("24963108.45"), "currency", "USD")),
        ("($250,000.00)", None, ParsedValue(D("-250000"), "currency", "USD")),
        ("1,234.5", None, ParsedValue(D("1234.5"), "number", None)),
        ("0.0123", "fraction", ParsedValue(D("0.0123"), "fraction", None)),
        ("250", "currency", ParsedValue(D("250"), "currency", None)),
        ("USD 313,174,253", None, ParsedValue(D("313174253"), "currency", "USD")),
        ("EUR 5.8bn", None, ParsedValue(D("5800000000"), "currency", "EUR")),
        ("1,234 GBP", None, ParsedValue(D("1234"), "currency", "GBP")),
        ("(USD 1,000)", None, ParsedValue(D("-1000"), "currency", "USD")),
        ("-USD 1,000", None, ParsedValue(D("-1000"), "currency", "USD")),
        ("3.87%*", None, ParsedValue(D("0.0387"), "fraction", None)),
        ("usd 12", None, ParsedValue(D("12"), "currency", "USD")),
        ("–0.45%", None, ParsedValue(D("-0.0045"), "fraction", None)),
        ("— 1.2%", None, ParsedValue(D("-0.012"), "fraction", None)),
        ("–$5m", None, ParsedValue(D("-5000000"), "currency", "USD")),
        ("$5", "percent", ParsedValue(D("5"), "currency", "USD")),
        ("USD 5", "percent", ParsedValue(D("5"), "currency", "USD")),
        ("5", "percent", ParsedValue(D("0.05"), "fraction", None)),
    ],
)
def test_parse_value(text, hint, expected):
    assert parse_value(text, hint) == expected


@pytest.mark.parametrize(
    "text", ["n/a", "N/A", "n/m", "N/M", "", "  ", "-", "–", "—", " – ", "— ", "garbage"]
)
def test_parse_value_placeholders_return_none(text):
    assert parse_value(text, None) is None


def test_parse_value_percent_unit_without_sign():
    assert parse_value("-0.5", "percent") == ParsedValue(D("-0.005"), "fraction", None)


@pytest.mark.parametrize(
    ("d", "kind", "expected"),
    [
        (date(2026, 1, 30), PeriodKind.month, date(2026, 1, 31)),
        (date(2026, 8, 28), PeriodKind.ytd, date(2026, 8, 31)),
        (date(2024, 2, 10), PeriodKind.month, date(2024, 2, 29)),
        (date(2026, 5, 3), PeriodKind.qtd, date(2026, 5, 31)),
        (date(2026, 12, 15), PeriodKind.y1, date(2026, 12, 31)),
        (date(2026, 1, 30), PeriodKind.other, date(2026, 1, 30)),
        (date(2026, 1, 30), PeriodKind.itd, date(2026, 1, 30)),
    ],
)
def test_snap_period_end(d, kind, expected):
    assert snap_period_end(d, kind) == expected
