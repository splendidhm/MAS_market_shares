"""Food procurement collection and reporting for the dashboard."""
import calendar
import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from threading import Lock
from time import sleep

from fastapi import HTTPException

from app.models import FoodBatch, FoodPage, RegistrationBatch, RegistrationPage
from app.services.g2b_api import G2BApiClient, G2BApiError, G2BAuthError, G2BRateLimitError
from app.services.quota_service import get_today_call_count, increment_today_call_count

# The service accepts a partial name in these fields. Unlisted categories
# can be entered by their official product classification name.
PRESETS = {
    "소시지류": ("dtilPrdctClsfcNoNm", "소시지"),
    "냉동감자": ("dtilPrdctClsfcNoNm", "냉동감자"),
    "냉동만두": ("dtilPrdctClsfcNoNm", "냉동만두"),
    "밀가루": ("dtilPrdctClsfcNoNm", "밀가루"),
    "조미김": ("dtilPrdctClsfcNoNm", "조미김"),
    "발효유": ("dtilPrdctClsfcNoNm", "발효유"),
    "고추장": ("dtilPrdctClsfcNoNm", "고추장"),
    "면류": ("dtilPrdctClsfcNoNm", "면류"),
}
# These business categories span multiple official names and use the full food cache.
GROUPS = {
    "김치": ("김치", "깍두기", "동치미", "석박지", "섞박지"),
    "장류": ("고추장", "된장", "간장", "혼합장", "청국장", "춘장"),
    "축산가공품": ("축산가공", "식육가공", "알가공", "유가공", "가공우유", "발효유", "치즈", "버터제품"),
    "빵류": ("빵", "케이크", "패스트리"),
    "과자류": ("과자", "비스킷", "쿠키", "크래커"),
}
sync_lock = Lock()


@dataclass(frozen=True)
class FoodCollection:
    batch_model: type
    page_model: type
    date_field: str


DELIVERIES = FoodCollection(FoodBatch, FoodPage, "dlvrReqRcptDate")
REGISTRATIONS = FoodCollection(RegistrationBatch, RegistrationPage, "rgstDt")


def is_food(row):
    code = str(row.get("prdctClsfcNo") or "").strip()
    return code.startswith("50") and not code.startswith("5021")


def criterion(category):
    for prefix, field in (("품명/", "prdctClsfcNoNm"), ("세부품명/", "dtilPrdctClsfcNoNm")):
        if category.startswith(prefix):
            return field, category[len(prefix):]
    return PRESETS.get(category, ("prdctClsfcNoNm", category)) if category else ("", "")


def parse_period(start, end):
    try:
        current = datetime.strptime(start, "%Y%m%d").date()
        last = datetime.strptime(end, "%Y%m%d").date()
    except ValueError:
        raise HTTPException(400, "유효한 시작일과 종료일을 입력해주세요.")
    if current > last:
        raise HTTPException(400, "조회 기간을 확인해주세요.")
    return current, last


def windows(start, end):
    current, last = parse_period(start, end)
    while current <= last:
        boundary = min(current.replace(day=calendar.monthrange(current.year, current.month)[1]), last)
        yield current.strftime("%Y%m%d"), boundary.strftime("%Y%m%d")
        if boundary == last:
            break
        current = boundary + timedelta(days=1)


def completed(db, start, end, category, source=DELIVERIES):
    model = source.batch_model
    return db.query(model).filter(
        model.start <= start, model.end >= end,
        model.scope.in_(["", category]), model.complete == 1
    ).order_by(model.id.desc()).first()


def sync_step(db, start, end, category, limit, refresh=False, *, source=DELIVERIES):
    batch_model, page_model = source.batch_model, source.page_model
    if category in GROUPS:
        category = ""
    # One page and its cursor are committed together. A second click or tab
    # observes that commit before choosing its next page.
    with sync_lock:
        periods = list(windows(start, end))
        if refresh:
            # A refresh stages replacement batches alongside completed copies.
            for a, b in periods:
                pending = db.query(batch_model).filter_by(start=a, end=b, scope=category, complete=0).first()
                if not pending:
                    db.add(batch_model(start=a, end=b, scope=category))
            db.commit()
        for idx, (a, b) in enumerate(periods):
            batch = db.query(batch_model).filter_by(start=a, end=b, scope=category, complete=0).first()
            if batch is None and completed(db, a, b, category, source):
                continue
            if get_today_call_count(db) >= limit:
                raise HTTPException(429, "일일 호출 한도에 도달했습니다. 같은 조건으로 다시 동기화하면 이어받습니다.")
            if batch is None:
                batch = batch_model(start=a, end=b, scope=category)
                db.add(batch)
                db.commit()
            client = G2BApiClient(registration=source == REGISTRATIONS)
            field, keyword = criterion(category)
            try:
                for attempt in range(3):
                    if get_today_call_count(db) >= limit:
                        raise HTTPException(429, "일일 한도에 도달했습니다. 다음 날 같은 조건으로 이어받을 수 있습니다.")
                    increment_today_call_count(db, 1)
                    try:
                        total, size, rows = client.fetch_page(a, b, batch.next_page, field, keyword)
                        break
                    except (G2BAuthError, G2BRateLimitError):
                        raise
                    except G2BApiError:
                        if attempt == 2:
                            raise
                        sleep(2 ** attempt)
            except G2BAuthError as exc:
                raise HTTPException(401, str(exc))
            except G2BRateLimitError as exc:
                raise HTTPException(429, str(exc))
            except G2BApiError as exc:
                raise HTTPException(502, str(exc))
            if batch.next_page > 1 and (batch.expected != total or (batch.next_page - 1) * size != batch.scanned):
                db.query(page_model).filter_by(batch_id=batch.id).delete()
                batch.next_page, batch.scanned = 1, 0
                db.commit()
                return {
                    "complete": False,
                    "progress": f"{a}~{b} 원천 건수 변경으로 첫 페이지부터 다시 확인합니다.",
                    "period_start": a,
                    "period_end": b,
                    "period_index": idx + 1,
                    "period_count": len(periods),
                    "current_page": 0,
                    "total_pages": max(1, (total + size - 1) // size),
                    "scanned": 0,
                    "expected": total,
                    "page_rows": 0,
                    "food_rows": 0,
                }
            foods = [r for r in rows if is_food(r)]
            page = batch.next_page
            db.add(page_model(batch_id=batch.id, number=page, records=json.dumps(foods, ensure_ascii=False)))
            batch.next_page += 1
            batch.scanned += len(rows)
            batch.expected = total
            batch.complete = int(batch.scanned == total)
            db.commit()
            return {
                "complete": bool(batch.complete and idx == len(periods)-1),
                "progress": f"{a}~{b} · {page}페이지 · 원천 {batch.scanned:,}/{total:,}건 확인",
                "period_start": a,
                "period_end": b,
                "period_index": idx + 1,
                "period_count": len(periods),
                "current_page": page,
                "total_pages": max(1, (total + size - 1) // size),
                "scanned": batch.scanned,
                "expected": total,
                "page_rows": len(rows),
                "food_rows": len(foods),
            }
        return {"complete": True, "progress": "선택 기간의 모든 페이지를 수집했습니다."}


def covered_batches(db, source, start, end, category):
    batches = []
    missing = []
    for a, b in windows(start, end):
        batch = completed(db, a, b, category, source)
        if not batch:
            missing.append(f"{a}~{b}")
        else:
            batches.append((a, b, batch.id))
    return batches, missing


def food_records(db, source, batches, category, classifications):
    field, keyword = criterion(category)
    model = source.page_model
    for a, b, batch_id in batches:
        pages = db.query(model.records).filter_by(batch_id=batch_id).order_by(model.number)
        for (records,) in pages.yield_per(5):
            for row in json.loads(records):
                day = str(row.get(source.date_field) or "").replace("-", "")[:8]
                if not is_food(row):
                    continue
                if not a <= day <= b:
                    continue
                if not category:
                    for prefix, key in (("품명", "prdctClsfcNoNm"), ("세부품명", "dtilPrdctClsfcNoNm")):
                        if row.get(key):
                            classifications.add(f"{prefix}/{row[key]}")
                if category in GROUPS:
                    names = f"{row.get('prdctClsfcNoNm', '')} {row.get('dtilPrdctClsfcNoNm', '')}"
                    if not any(term in names for term in GROUPS[category]):
                        continue
                elif field and keyword not in str(row.get(field) or ""):
                    continue
                if category.startswith(("품명/", "세부품명/")) and keyword != row.get(field):
                    continue
                yield row


def report(db, start, end, category, company, product, on_record=None):
    batches, missing = covered_batches(db, DELIVERIES, start, end, category)
    if missing:
        return {"complete": False, "missing": missing, "company_rank": [], "product_rows": [], "chart_data": [], "total_amount": None}
    company_amount = defaultdict(int)
    product_amount = defaultdict(int)
    classifications = set()
    for row in food_records(db, DELIVERIES, batches, category, classifications):
        vendor = str(row.get("corpNm") or "업체명 미제공")
        name = str(row.get("prdctIdntNoNm") or row.get("dtilPrdctClsfcNoNm") or "품목명 미제공")
        if company.casefold() not in vendor.casefold() or product.casefold() not in name.casefold():
            continue
        # Changes/cancellations contribute their signed delta on the receipt date.
        value = row.get("incdecAmt")
        if value in (None, ""):
            value = row.get("prdctAmt") or 0
        amount = int(str(value).replace(",", ""))
        company_amount[vendor] += amount
        product_amount[(vendor, str(row.get("prdctIdntNo") or ""), name)] += amount
        if on_record:
            on_record(row)
    total = sum(company_amount.values())
    ranks = []
    running = 0
    for rank, (vendor, amount) in enumerate(sorted(company_amount.items(), key=lambda x: -x[1]), 1):
        running += amount
        ranks.append(dict(rank=rank, company=vendor, amount=amount,
                          share=round(amount*100/total, 2) if total else 0,
                          cumulative_share=round(running*100/total, 2) if total else 0))
    products = [dict(company=k[0], code=k[1], product=k[2], amount=v)
                for k,v in sorted(product_amount.items(), key=lambda x: -x[1])]
    items = defaultdict(int)
    for (vendor, code, name), amount in product_amount.items():
        items[(code, name)] += amount
    item_rows = [dict(code=k[0], product=k[1], amount=v)
                 for k, v in sorted(items.items(), key=lambda x: -x[1])]
    return dict(item_rows=item_rows, complete=True, cache_hit=True, total_amount=total, company_rank=ranks,
                product_rows=products, categories=sorted(classifications), chart_data=ranks[:10])
