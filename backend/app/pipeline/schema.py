"""Pydantic schemas the LLM must fill.

Every model is OpenAI strict-json_schema compatible: all fields required (optional
values are ``X | None`` with no default), no unions beyond nullable, no constraints
the strict subset rejects. Counts such as "3-8 tags" live in the prompt instead.
"""

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.models import DocType, EntityKind, Measure, PeriodKind
from app.values import UnitHint

__all__ = [
    "CsvMapping", "DocumentExtraction", "FundRef", "Override", "RowOut", "TableOut",
    "UnitHint", "ValueColumn",
]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FundRef(_Strict):
    name: str
    share_class: str | None


class TableOut(_Strict):
    title: str | None
    header: list[list[str]]
    rows: list[list[str]]


class RowOut(_Strict):
    entity: str
    entity_kind: EntityKind
    share_class: str | None
    measure: Measure
    period_kind: PeriodKind
    period_end: date
    value_as_written: str
    unit_hint: UnitHint
    currency: str | None
    benchmark_name: str | None
    table_index: int | None
    row_index: int | None
    col_index: int | None


class DocumentExtraction(_Strict):
    doc_type: DocType
    manager: str | None
    funds: list[FundRef]
    as_of_date: date | None
    currency: str | None
    summary: str
    tags: list[str]
    tables: list[TableOut]
    rows: list[RowOut]


class ValueColumn(_Strict):
    column: str
    measure: Measure
    period_kind: PeriodKind
    unit_hint: UnitHint
    benchmark_name: str | None


class Override(_Strict):
    entity: str
    period_kind: PeriodKind
    period_end: date


class CsvMapping(_Strict):
    layout: Literal["long", "wide"]
    skip_top: int
    skip_bottom: int
    entity_column: str | None
    constant_entity: str | None
    share_class_column: str | None
    date_column: str | None
    period_columns: list[str]
    value_columns: list[ValueColumn]
    date_format: str | None
    period_end_overrides: list[Override]
