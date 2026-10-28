from typing import Literal, Optional
from pydantic import BaseModel
from schema import Fund, PrintedTable
class LRow(BaseModel):
    fund_index: int
    entity_kind: Literal["fund","account"]
    measure: Literal["return","benchmark_return","aum","nav","account_value","account_return"]
    period_kind: Literal["month","qtd","ytd","1y","3y","5y","itd","calendar_year","other"]
    period_end: str
    value_as_written: str
    unit: Literal["percent","currency","bps","price","other"]
    benchmark_name: Optional[str]
    table_index: Optional[int]
    row: Optional[int]
    col: Optional[int]
class LeanExtraction(BaseModel):
    doc_type: Literal["factsheet","performance_report","statement","investor_letter","other"]
    manager: str
    funds: list[Fund]
    as_of_date: str
    currency: Optional[str]
    summary: str
    tags: list[str]
    tables: list[PrintedTable]
    rows: list[LRow]
