"""One-off converter: spike model output -> the production schema.

Run from the repo root:  python backend/tests/recorded/_convert.py
Reads docs/03-implementation-plan/spike/out/{cur_*,map_*}.json (and the fixture
CSVs for mapping details the old shape stored differently) and writes the
converted results next to this file. Kept so the recorded data is reproducible;
the outputs are committed, so tests never need to re-run it.

Extraction mapping (spike -> app.pipeline.schema.DocumentExtraction):
  tables[].header_rows/body_rows -> header/rows
  row.value, row.unit dropped; unit_hint derived from measure:
      return / benchmark_return / account_return -> percent (every recorded
      document prints these as percentages, with or without a % sign)
      aum / account_value -> currency ; nav -> number
  row.row/col -> row_index/col_index
  period_kind calendar_year -> 1y, period_end = 31 Dec of that year
  aum / nav / account_value -> period_kind other (at their as-of date)
Mapping (spike CsvMapping -> new CsvMapping): header_row_index -> skip_top;
  footer prefixes -> skip_bottom (counted on the fixture CSV, including the blank
  line before the footnotes); wide_date_columns -> period_columns; wide_date_format
  -> date_format; unit percent_number/percent_string -> percent; the per-column
  benchmark_name_column is replaced by the constant name found in that CSV column;
  period_end_literal is dropped (the wide YTD end is the latest period column);
  overrides gain period_kind from the overridden column.
"""

import csv
import json
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SPIKE_OUT = ROOT / "docs/03-implementation-plan/spike/out"
FIXTURES = ROOT / "fixtures"
HERE = Path(__file__).resolve().parent

PERCENT_MEASURES = {"return", "benchmark_return", "account_return"}
POINT_IN_TIME = {"aum", "nav", "account_value"}
COLUMN_PERIOD_KIND = {"YTD": "ytd"}


def unit_hint(measure: str) -> str:
    if measure in PERCENT_MEASURES:
        return "percent"
    return "currency" if measure in {"aum", "account_value"} else "number"


def convert_row(r: dict) -> dict:
    kind, end = r["period_kind"], r["period_end"]
    if r["measure"] in POINT_IN_TIME:
        kind = "other"
    elif kind == "calendar_year":
        kind, end = "1y", f"{end[:4]}-12-31"
    return {
        "entity": r["entity"], "entity_kind": r["entity_kind"], "share_class": r["share_class"],
        "measure": r["measure"], "period_kind": kind, "period_end": end,
        "value_as_written": r["value_as_written"], "unit_hint": unit_hint(r["measure"]),
        "currency": r["currency"], "benchmark_name": r["benchmark_name"],
        "table_index": r["table_index"], "row_index": r["row"], "col_index": r["col"],
    }


def convert_extraction(d: dict) -> dict:
    date.fromisoformat(d["as_of_date"])
    return {
        "doc_type": d["doc_type"], "manager": d["manager"] or None, "funds": d["funds"],
        "as_of_date": d["as_of_date"], "currency": d["currency"], "summary": d["summary"],
        "tags": d["tags"],
        "tables": [
            {"title": t["title"], "header": t["header_rows"], "rows": t["body_rows"]}
            for t in d["tables"]
        ],
        "rows": [convert_row(r) for r in d["rows"]],
    }


def _fixture_csv(stem: str) -> Path:
    return next(FIXTURES.rglob(stem + ".csv"))


def convert_mapping(stem: str, m: dict) -> dict:
    lines = _fixture_csv(stem).read_text(encoding="utf-8-sig").splitlines()
    prefixes = tuple(m["skip_footer_starting_with"])
    skip_bottom = 0
    if prefixes:
        first = next(i for i, l in enumerate(lines) if i > m["header_row_index"] and l.startswith(prefixes))
        while first > 0 and not lines[first - 1].strip(", "):
            first -= 1  # blank spacer lines above the footnotes
        skip_bottom = len(lines) - first
    rows = list(csv.DictReader(lines[m["header_row_index"]:]))

    def bench(col: str | None) -> str | None:
        if not col:
            return None
        names = {r[col] for r in rows if r.get(col)}
        return names.pop() if len(names) == 1 else None

    return {
        "layout": m["layout"], "skip_top": m["header_row_index"], "skip_bottom": skip_bottom,
        "entity_column": m["entity_column"], "constant_entity": None,
        "share_class_column": m["share_class_column"], "date_column": m["date_column"],
        "period_columns": m["wide_date_columns"],
        "value_columns": [
            {
                "column": v["column"], "measure": v["measure"], "period_kind": v["period_kind"],
                "unit_hint": "currency" if v["unit"] == "currency" else (
                    "fraction" if v["unit"] == "fraction" else "percent"),
                "benchmark_name": bench(v["benchmark_name_column"]),
            }
            for v in m["value_columns"]
        ],
        "date_format": m["wide_date_format"],
        "period_end_overrides": [
            {"entity": o["entity"], "period_kind": COLUMN_PERIOD_KIND[o["column"]],
             "period_end": o["period_end"]}
            for o in m["period_end_overrides"]
        ],
    }


def main() -> None:
    for f in sorted(SPIKE_OUT.glob("cur_*.json")):
        out = HERE / f.name.removeprefix("cur_")
        out.write_text(json.dumps(convert_extraction(json.loads(f.read_text())), indent=1) + "\n")
        print("wrote", out.name)
    for f in sorted(SPIKE_OUT.glob("map_*.json")):
        stem = f.stem.removeprefix("map_")
        out = HERE / f.name
        out.write_text(json.dumps(convert_mapping(stem, json.loads(f.read_text())), indent=1) + "\n")
        print("wrote", out.name)


if __name__ == "__main__":
    main()
