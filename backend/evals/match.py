"""Lenient scoring of extracted rows against a fixture's ``.truth.json`` (spec A10). Pure; no I/O beyond load_truth."""

import calendar
import json
import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path

TOLERANCE = Decimal("0.00005")
_CURRENCIES = {"eur", "usd", "gbp"}
_ENTITY_NOISE = {"lp", "ltd", "llc", "fund", "l", "p"}


@dataclass(frozen=True)
class TruthRow:
    entity: str
    share_class: str | None
    measure: str
    period_kind: str
    period_end: date
    value: Decimal


@dataclass(frozen=True)
class Got:
    """An extracted row as the scorer sees it (``RowDraft`` has the same fields and works too)."""

    entity: str
    share_class: str | None
    measure: str
    period_kind: str
    period_end: date
    value: Decimal


@dataclass(frozen=True)
class Score:
    hits: int
    total: int
    got_count: int
    partial: bool
    misses: list[TruthRow]
    extras: list[Got]

    @property
    def recall(self) -> float:
        return self.hits / self.total if self.total else 1.0

    @property
    def precision(self) -> float | None:
        """None for partial truth files: unlisted rows may still be correct."""
        if self.partial:
            return None
        return (self.got_count - len(self.extras)) / self.got_count if self.got_count else 1.0


def _tokens(text: str | None) -> set[str]:
    text = re.sub(r"\(.*?\)", "", text or "").lower().replace("&", " and ")
    return set(re.sub(r"[^a-z0-9 ]", " ", text).split())


def _entity_tokens(text: str) -> set[str]:
    return _tokens(text) - _ENTITY_NOISE


def _class_tokens(text: str | None) -> set[str]:
    return _tokens(text) - {"class"} - _CURRENCIES


def _contains(a: set[str], b: set[str]) -> bool:
    return a <= b or b <= a


def month_end(d: date) -> date:
    return d.replace(day=calendar.monthrange(d.year, d.month)[1])


def _same(t: TruthRow, g: Got) -> bool:
    if t.measure != g.measure or t.period_kind != g.period_kind:
        return False
    if abs(g.value - t.value) > TOLERANCE or month_end(g.period_end) != month_end(t.period_end):
        return False
    if not _contains(_entity_tokens(t.entity), _entity_tokens(g.entity)):
        return False
    tc, gc = _class_tokens(t.share_class), _class_tokens(g.share_class)
    return not tc or not gc or _contains(tc, gc)


def match(truth: list[TruthRow], got: list[Got], *, partial: bool = False) -> Score:
    used: set[int] = set()
    misses: list[TruthRow] = []
    hits = 0
    for t in truth:
        found = next((i for i, g in enumerate(got) if _same(t, g)), None)
        if found is None:
            misses.append(t)
            continue
        hits += 1
        used.add(found)
    # a row matching some truth row (even a second one) is not an extra
    extras = [g for i, g in enumerate(got) if i not in used and not any(_same(t, g) for t in truth)]
    return Score(hits, len(truth), len(got), partial, misses, extras)


def load_truth(path: Path) -> tuple[list[TruthRow], bool]:
    data = json.loads(Path(path).read_text())
    rows = [
        TruthRow(
            o["fund"], o["share_class"], o["metric"], o["period_kind"],
            date.fromisoformat(o["period_end"]), Decimal(o["value"]),
        )
        for o in data["observations"]
    ]
    return rows, bool(data.get("partial"))
