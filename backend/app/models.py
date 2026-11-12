from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class RawDelivery(Base):
    __tablename__ = "raw_deliveries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    period_month: Mapped[str] = mapped_column(String(7), index=True)
    category_main: Mapped[str] = mapped_column(String(100), default="")
    category_sub: Mapped[str] = mapped_column(String(100), default="")
    manufacturer: Mapped[str] = mapped_column(String(150), index=True)
    item_code: Mapped[str] = mapped_column(String(100), index=True, default="")
    item_name: Mapped[str] = mapped_column(String(150), default="")
    spec: Mapped[str] = mapped_column(String(150), default="")
    quantity: Mapped[float] = mapped_column(Float, default=0.0)
    amount: Mapped[float] = mapped_column(Float, default=0.0)
    region: Mapped[str] = mapped_column(String(100), default="")
    military_branch: Mapped[str] = mapped_column(String(40), default="")
    contract_no: Mapped[str] = mapped_column(String(120), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class QueryCache(Base):
    __tablename__ = "query_cache"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    query_key: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    response_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class G2BCachedRow(Base):
    __tablename__ = "g2b_cached_rows"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    period_yyyymm: Mapped[str] = mapped_column(String(6), index=True)
    source_key: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    company: Mapped[str] = mapped_column(String(200), index=True, default="")
    product_name: Mapped[str] = mapped_column(String(500), default="")
    category_code: Mapped[str] = mapped_column(String(20), index=True, default="")
    category_name: Mapped[str] = mapped_column(String(200), default="")
    amount: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ApiDailyUsage(Base):
    __tablename__ = "api_daily_usage"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    usage_date: Mapped[str] = mapped_column(String(10), unique=True, index=True)
    call_count: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class BatchColumns:
    id: Mapped[int] = mapped_column(primary_key=True)
    scope: Mapped[str] = mapped_column(String(100), index=True)
    start: Mapped[str] = mapped_column(String(8), index=True)
    end: Mapped[str] = mapped_column(String(8))
    next_page: Mapped[int] = mapped_column(default=1)
    scanned: Mapped[int] = mapped_column(default=0)
    expected: Mapped[int] = mapped_column(default=0)
    complete: Mapped[int] = mapped_column(default=0)


class PageColumns:
    batch_id: Mapped[int] = mapped_column(primary_key=True)
    number: Mapped[int] = mapped_column(primary_key=True)
    # Only food records are persisted, including all fields provided by PPS.
    records: Mapped[str] = mapped_column(Text)


class FoodBatch(BatchColumns, Base):
    __tablename__ = "food_batches"


class FoodPage(PageColumns, Base):
    __tablename__ = "food_pages"


class RegistrationBatch(BatchColumns, Base):
    __tablename__ = "registration_batches"


class RegistrationPage(PageColumns, Base):
    __tablename__ = "registration_pages"
