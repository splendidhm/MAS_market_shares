from typing import List

from pydantic import BaseModel, Field


class MarketShareQuery(BaseModel):
    start_month: str = Field(..., pattern=r"^\d{4}-\d{2}$")
    end_month: str = Field(..., pattern=r"^\d{4}-\d{2}$")
    item_code: str = ""
    manufacturer_name: str = ""
    top_n: int = 10
    use_dummy: bool = True


class TableRow(BaseModel):
    rank: int
    category_main: str
    category_sub: str
    manufacturer: str
    item_name: str
    spec: str
    quantity: float
    amount: float
    market_share: float
    cumulative_share: float
    mom_change_rate: float


class ChartRow(BaseModel):
    manufacturer: str
    market_share: float


class DashboardResponse(BaseModel):
    total_amount: float
    table_rows: List[TableRow]
    chart_rows: List[ChartRow]
    cache_hit: bool = False
