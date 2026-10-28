from typing import Literal, Optional
from pydantic import BaseModel
class Fund(BaseModel):
    name: str
    share_class: Optional[str]
class PrintedTable(BaseModel):
    title: Optional[str]
    header_rows: list[list[str]]
    body_rows: list[list[str]]
class CommonRow(BaseModel):
    entity: str
    entity_kind: Literal["fund","account"]
    share_class: Optional[str]
    measure: Literal["return","benchmark_return","aum","nav","account_value","account_return"]
    period_kind: Literal["month","qtd","ytd","1y","3y","5y","itd","calendar_year","other"]
    period_end: str   # YYYY-MM-DD
    value_as_written: str
    value: Optional[float]
    unit: Literal["fraction","currency","bps","price","other"]
    currency: Optional[str]
    benchmark_name: Optional[str]
    table_index: Optional[int]
    row: Optional[int]
    col: Optional[int]
class Extraction(BaseModel):
    doc_type: Literal["factsheet","performance_report","statement","investor_letter","other"]
    manager: str
    funds: list[Fund]
    as_of_date: str
    currency: Optional[str]
    summary: str
    tags: list[str]
    tables: list[PrintedTable]
    rows: list[CommonRow]

# CSV column mapping
class ValueCol(BaseModel):
    column: str
    measure: Literal["return","benchmark_return","aum","nav"]
    period_kind: Literal["month","qtd","ytd","1y","3y","5y","itd","calendar_year","other"]
    unit: Literal["percent_number","fraction","percent_string","currency","other"]
    benchmark_name_column: Optional[str]
    period_end_literal: Optional[str]
class Override(BaseModel):
    entity: str
    column: str
    period_end: str
class CsvMapping(BaseModel):
    layout: Literal["long","wide"]
    header_row_index: int
    skip_footer_starting_with: list[str]
    entity_column: str
    share_class_column: Optional[str]
    date_column: Optional[str]          # long layout
    wide_date_columns: list[str]         # wide layout: month columns like Jan-26
    wide_date_format: Optional[str]      # e.g. %b-%y
    value_columns: list[ValueCol]
    document_currency: Optional[str]
    period_end_overrides: list[Override]
