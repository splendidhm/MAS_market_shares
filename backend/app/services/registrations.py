from datetime import datetime, timedelta, timezone

from fastapi import HTTPException

from app.services.food_report import REGISTRATIONS, covered_batches, food_records, parse_period


def available_period(start, end):
    first, last = parse_period(start, end)
    # PPS publishes registrations through the previous Korean calendar day.
    latest = datetime.now(timezone(timedelta(hours=9))).date() - timedelta(days=1)
    if first > latest:
        raise HTTPException(400, "등록 내역은 어제 등록분까지 조회할 수 있습니다.")
    return start, min(last, latest).strftime("%Y%m%d")


def registration_report(db, start, end, category, company, product, page, page_size):
    records, missing, classifications = registration_records(
        db, start, end, category, company, product
    )
    if missing:
        return dict(complete=False, missing=missing, rows=[], total=None, categories=[], through=end)

    rows = []
    total = 0
    offset = (page - 1) * page_size
    for row in records:
        if offset <= total < offset + page_size:
            rows.append(row)
        total += 1
    return dict(complete=True, rows=rows, total=total, categories=sorted(classifications), through=end)


def registration_records(db, start, end, category, company="", product=""):
    batches, missing = covered_batches(db, REGISTRATIONS, start, end, category)
    if missing:
        return iter(()), missing, set()

    classifications = set()
    company, product = company.strip().casefold(), product.strip().casefold()

    def matching_records():
        for row in food_records(db, REGISTRATIONS, reversed(batches), category, classifications):
            if company and not any(company in str(row.get(key) or "").casefold()
                                   for key in ("cntrctCorpNm", "prdctMakrNm")):
                continue
            if product and not any(product in str(row.get(key) or "").casefold()
                                   for key in ("prdctSpecNm", "prdctIdntNo")):
                continue
            yield row

    return matching_records(), [], classifications
