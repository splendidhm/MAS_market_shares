from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.models import ApiDailyUsage


def today_key() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def get_today_call_count(db: Session) -> int:
    key = today_key()
    row = db.query(ApiDailyUsage).filter(ApiDailyUsage.usage_date == key).first()
    if not row:
        return 0
    return int(row.call_count or 0)


def increment_today_call_count(db: Session, amount: int = 1) -> int:
    key = today_key()
    row = db.query(ApiDailyUsage).filter(ApiDailyUsage.usage_date == key).first()
    if not row:
        row = ApiDailyUsage(usage_date=key, call_count=0)
        db.add(row)
        db.flush()
    row.call_count = int(row.call_count or 0) + max(0, int(amount))
    db.commit()
    return int(row.call_count or 0)
