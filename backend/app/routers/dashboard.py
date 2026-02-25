from __future__ import annotations

import calendar
from datetime import datetime
import os
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import G2BCachedRow, RawDelivery
from app.schemas import DashboardResponse
from app.services.api_client import ApiQueryParams, OpenApiAuthError, OpenApiError, ProcurementApiClient
from app.services.cache_service import get_cached_result, make_query_key, upsert_cache_result
from app.services.data_processor import DataProcessor, process_market_share
from app.services.excel_exporter import create_excel
from app.services.g2b_api import G2BApiClient, G2BApiError, G2BAuthError, G2BRateLimitError
from app.services.quota_service import get_today_call_count, increment_today_call_count

router = APIRouter(prefix="/api", tags=["dashboard"])
DAILY_CALL_LIMIT = int(os.getenv("G2B_DAILY_CALL_LIMIT", "900"))
DAILY_WARNING_THRESHOLD = int(os.getenv("G2B_DAILY_WARNING_THRESHOLD", "850"))


def _validate_month_range(start_month: str, end_month: str) -> None:
    try:
        start_dt = datetime.strptime(start_month, "%Y-%m")
        end_dt = datetime.strptime(end_month, "%Y-%m")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="월 형식은 YYYY-MM 이어야 합니다.") from exc

    if start_dt > end_dt:
        raise HTTPException(status_code=400, detail="조회 시작월은 종료월보다 이전이어야 합니다.")


def _iter_months(start_yyyymm: str, end_yyyymm: str) -> List[str]:
    months: List[str] = []
    current = datetime.strptime(start_yyyymm, "%Y%m")
    end = datetime.strptime(end_yyyymm, "%Y%m")
    while current <= end:
        months.append(current.strftime("%Y%m"))
        year = current.year + (1 if current.month == 12 else 0)
        month = 1 if current.month == 12 else current.month + 1
        current = current.replace(year=year, month=month)
    return months


def _yyyymm_to_date_range(start_month: str, end_month: str) -> tuple[str, str]:
    s_year = int(start_month[:4])
    s_month = int(start_month[4:6])
    e_year = int(end_month[:4])
    e_month = int(end_month[4:6])
    e_last_day = calendar.monthrange(e_year, e_month)[1]
    return f"{s_year:04d}{s_month:02d}01", f"{e_year:04d}{e_month:02d}{e_last_day:02d}"


def _resolve_period_inputs(
    start_month: Optional[str],
    end_month: Optional[str],
    start_date: Optional[str],
    end_date: Optional[str],
) -> tuple[str, str]:
    if start_date and end_date:
        if start_date > end_date:
            raise HTTPException(status_code=400, detail="startDate는 endDate보다 작거나 같아야 합니다.")
        return start_date, end_date
    if start_month and end_month:
        if start_month > end_month:
            raise HTTPException(status_code=400, detail="startMonth는 endMonth보다 작거나 같아야 합니다.")
        return _yyyymm_to_date_range(start_month, end_month)
    raise HTTPException(status_code=400, detail="startDate/endDate 또는 startMonth/endMonth를 함께 전달해야 합니다.")


def _extract_yyyymm(row: Dict[str, Any]) -> str:
    date_text = str(row.get("dlvrReqRcptDate", "") or "").strip()
    if len(date_text) >= 7 and "-" in date_text:
        return date_text[:4] + date_text[5:7]
    raw = str(row.get("IntlCntrctDlvrReqDate", "") or "").strip()
    if len(raw) >= 6 and raw.isdigit():
        return raw[:6]
    return ""


def _normalize_amount(value: Any) -> float:
    text = str(value or "").replace(",", "").strip()
    if not text:
        return 0.0
    try:
        return float(text)
    except ValueError:
        return 0.0


def _build_source_key(row: Dict[str, Any]) -> str:
    return "|".join(
        [
            str(row.get("dlvrReqNo", "") or ""),
            str(row.get("dlvrReqChgOrd", "") or ""),
            str(row.get("prdctSno", "") or ""),
            str(row.get("prdctIdntNo", "") or ""),
            str(row.get("IntlCntrctDlvrReqDate", "") or ""),
        ]
    )


def _extract_yyyymmdd_from_source_key(source_key: str) -> str:
    parts = str(source_key or "").split("|")
    last = parts[-1].strip() if parts else ""
    if len(last) == 8 and last.isdigit():
        return last
    return ""


def _sync_month_if_needed(
    db: Session,
    month: str,
    force: bool = False,
    request_guard: Any = None,
    request_record: Any = None,
) -> Dict[str, int]:
    existing_count = db.query(G2BCachedRow).filter(G2BCachedRow.period_yyyymm == month).count()
    if existing_count > 0 and not force:
        return {"month": month, "fetched": 0, "saved": 0, "skipped": existing_count}

    if force and existing_count > 0:
        db.query(G2BCachedRow).filter(G2BCachedRow.period_yyyymm == month).delete()
        db.commit()

    client = G2BApiClient()
    raw_items = client.fetch_sales_data(
        start_month=month,
        end_month=month,
        category_filter="",
        request_guard=request_guard,
        request_record=request_record,
    )
    if not raw_items:
        return {"month": month, "fetched": 0, "saved": 0, "skipped": 0}

    to_insert: List[G2BCachedRow] = []
    for row in raw_items:
        period_yyyymm = _extract_yyyymm(row)
        source_key = _build_source_key(row)
        if not period_yyyymm or not source_key:
            continue

        to_insert.append(
            G2BCachedRow(
                period_yyyymm=period_yyyymm,
                source_key=source_key,
                company=str(row.get("corpNm", "") or "").strip(),
                product_name=str(row.get("prdctIdntNoNm", "") or "").strip(),
                category_code=str(row.get("prdctClsfcNo", "") or "").strip(),
                category_name=str(row.get("prdctClsfcNoNm", "") or "").strip(),
                amount=_normalize_amount(row.get("prdctAmt")),
            )
        )

    if not to_insert:
        return {"month": month, "fetched": len(raw_items), "saved": 0, "skipped": 0}

    saved = 0
    for row in to_insert:
        try:
            db.add(row)
            db.commit()
            saved += 1
        except Exception:
            db.rollback()
            continue

    return {"month": month, "fetched": len(raw_items), "saved": saved, "skipped": 0}


def _build_db_dashboard(
    db: Session,
    start_date: str,
    end_date: str,
    category: str,
    company: str,
    product_name: str,
) -> Dict[str, Any]:
    start_month = start_date[:6]
    end_month = end_date[:6]
    query = db.query(G2BCachedRow).filter(
        G2BCachedRow.period_yyyymm >= start_month,
        G2BCachedRow.period_yyyymm <= end_month,
    )
    rows = [
        row
        for row in query.all()
        if (
            (_extract_yyyymmdd_from_source_key(row.source_key) or f"{row.period_yyyymm}01")
            >= start_date
        )
        and (
            (_extract_yyyymmdd_from_source_key(row.source_key) or f"{row.period_yyyymm}01")
            <= end_date
        )
    ]
    if not rows:
        return {"total_amount": 0.0, "company_rank": [], "chart_data": [], "cache_hit": True, "source": "db"}

    raw_items = [
        {
            "corpNm": row.company,
            "prdctAmt": row.amount,
            "prdctClsfcNo": row.category_code,
            "prdctClsfcNoNm": row.category_name,
            "prdctIdntNoNm": row.product_name,
        }
        for row in rows
    ]
    total_amount, company_rank, chart_data = process_market_share(
        raw_items,
        company_filter=company,
        category_filter=category,
        product_filter=product_name,
    )
    return {
        "total_amount": total_amount,
        "company_rank": company_rank,
        "chart_data": chart_data,
        "cache_hit": True,
        "source": "db",
    }


def _save_raw_rows(db: Session, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    db_rows = [
        RawDelivery(
            period_month=row.get("period_month", ""),
            category_main=row.get("category_main", ""),
            category_sub=row.get("category_sub", ""),
            manufacturer=row.get("manufacturer", ""),
            item_code=row.get("item_code", ""),
            item_name=row.get("item_name", ""),
            spec=row.get("spec", ""),
            quantity=float(row.get("quantity", 0)),
            amount=float(row.get("amount", 0)),
            region=row.get("region", ""),
            military_branch=row.get("military_branch", ""),
            contract_no=row.get("contract_no", ""),
        )
        for row in rows
    ]
    db.bulk_save_objects(db_rows)
    db.commit()


def _build_result(
    db: Session,
    start_month: str,
    end_month: str,
    item_code: str,
    manufacturer_name: str,
    top_n: int,
    use_dummy: bool,
) -> Dict[str, Any]:
    query_payload = {
        "start_month": start_month,
        "end_month": end_month,
        "item_code": item_code,
        "manufacturer_name": manufacturer_name,
        "top_n": top_n,
        "use_dummy": use_dummy,
    }

    query_key = make_query_key(query_payload)
    cached = get_cached_result(db, query_key)
    if cached:
        cached["cache_hit"] = True
        return cached

    client = ProcurementApiClient()
    processor = DataProcessor()

    try:
        rows = client.fetch(
            ApiQueryParams(
                start_month=start_month,
                end_month=end_month,
                item_code=item_code,
                manufacturer_name=manufacturer_name,
            ),
            use_dummy=use_dummy,
        )
    except OpenApiAuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except OpenApiError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    if not rows:
        raise HTTPException(status_code=404, detail="조회된 데이터가 없습니다.")

    _save_raw_rows(db, rows)
    table_rows, chart_rows, total_amount = processor.build_dashboard(rows, start_month, end_month, top_n)

    result = {
        "total_amount": total_amount,
        "table_rows": table_rows,
        "chart_rows": chart_rows,
        "cache_hit": False,
    }
    upsert_cache_result(db, query_key, result)
    return result


@router.get("/dashboard")
def get_dashboard(
    startMonth: Optional[str] = Query(None, pattern=r"^\d{6}$", description="조회 시작월 (YYYYMM)"),
    endMonth: Optional[str] = Query(None, pattern=r"^\d{6}$", description="조회 종료월 (YYYYMM)"),
    startDate: Optional[str] = Query(None, pattern=r"^\d{8}$", description="조회 시작일 (YYYYMMDD)"),
    endDate: Optional[str] = Query(None, pattern=r"^\d{8}$", description="조회 종료일 (YYYYMMDD)"),
    category: str = Query("", description="카테고리명 또는 품목코드"),
    company: str = Query("", description="회사명 필터"),
    productName: str = Query("", description="제품명 필터"),
    db: Session = Depends(get_db),
):
    resolved_start_date, resolved_end_date = _resolve_period_inputs(startMonth, endMonth, startDate, endDate)
    return _build_db_dashboard(
        db=db,
        start_date=resolved_start_date,
        end_date=resolved_end_date,
        category=category,
        company=company,
        product_name=productName,
    )


@router.post("/dashboard/sync")
def sync_dashboard_cache(
    startMonth: Optional[str] = Query(None, pattern=r"^\d{6}$", description="동기화 시작월 (YYYYMM)"),
    endMonth: Optional[str] = Query(None, pattern=r"^\d{6}$", description="동기화 종료월 (YYYYMM)"),
    startDate: Optional[str] = Query(None, pattern=r"^\d{8}$", description="동기화 시작일 (YYYYMMDD)"),
    endDate: Optional[str] = Query(None, pattern=r"^\d{8}$", description="동기화 종료일 (YYYYMMDD)"),
    force: bool = Query(False, description="기존 월 데이터를 삭제 후 재수집"),
    db: Session = Depends(get_db),
):
    resolved_start_date, resolved_end_date = _resolve_period_inputs(startMonth, endMonth, startDate, endDate)

    used_calls = get_today_call_count(db)
    if used_calls >= DAILY_CALL_LIMIT:
        raise HTTPException(
            status_code=429,
            detail=f"일일 API 호출 한도({DAILY_CALL_LIMIT})를 초과했습니다. 내일 다시 시도해주세요.",
        )

    def _request_guard() -> None:
        nonlocal used_calls
        if used_calls >= DAILY_CALL_LIMIT:
            raise G2BRateLimitError(
                f"일일 API 호출 한도({DAILY_CALL_LIMIT})에 도달하여 동기화를 중단했습니다."
            )

    def _request_record() -> None:
        nonlocal used_calls
        used_calls = increment_today_call_count(db, 1)

    months = _iter_months(resolved_start_date[:6], resolved_end_date[:6])
    report: List[Dict[str, Any]] = []
    for month in months:
        try:
            report.append(
                _sync_month_if_needed(
                    db,
                    month=month,
                    force=force,
                    request_guard=_request_guard,
                    request_record=_request_record,
                )
            )
        except G2BRateLimitError as exc:
            raise HTTPException(status_code=429, detail=str(exc)) from exc
        except G2BAuthError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
        except G2BApiError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    remaining_calls = max(DAILY_CALL_LIMIT - used_calls, 0)
    warning_message = ""
    if used_calls >= DAILY_WARNING_THRESHOLD:
        warning_message = (
            f"[경고] 오늘 API 호출량 {used_calls}회 사용. "
            f"일일 한도 {DAILY_CALL_LIMIT}회까지 {remaining_calls}회 남았습니다."
        )
    return {
        "synced_range": {"start_date": resolved_start_date, "end_date": resolved_end_date},
        "synced_months": report,
        "daily_call_count": used_calls,
        "daily_call_limit": DAILY_CALL_LIMIT,
        "remaining_calls": remaining_calls,
        "warning_message": warning_message,
    }


@router.get("/dashboard/usage")
def get_dashboard_usage(db: Session = Depends(get_db)):
    used_calls = get_today_call_count(db)
    remaining_calls = max(DAILY_CALL_LIMIT - used_calls, 0)
    warning_message = ""
    if used_calls >= DAILY_WARNING_THRESHOLD:
        warning_message = (
            f"[경고] 오늘 API 호출량 {used_calls}회 사용. "
            f"일일 한도 {DAILY_CALL_LIMIT}회까지 {remaining_calls}회 남았습니다."
        )
    return {
        "daily_call_count": used_calls,
        "daily_call_limit": DAILY_CALL_LIMIT,
        "remaining_calls": remaining_calls,
        "warning_message": warning_message,
    }


@router.get("/dashboard/excel")
def download_dashboard_excel(
    startMonth: Optional[str] = Query(None, pattern=r"^\d{6}$", description="조회 시작월 (YYYYMM)"),
    endMonth: Optional[str] = Query(None, pattern=r"^\d{6}$", description="조회 종료월 (YYYYMM)"),
    startDate: Optional[str] = Query(None, pattern=r"^\d{8}$", description="조회 시작일 (YYYYMMDD)"),
    endDate: Optional[str] = Query(None, pattern=r"^\d{8}$", description="조회 종료일 (YYYYMMDD)"),
    category: str = Query("", description="카테고리명 또는 품목코드"),
    company: str = Query("", description="회사명 필터"),
    productName: str = Query("", description="제품명 필터"),
    db: Session = Depends(get_db),
):
    resolved_start_date, resolved_end_date = _resolve_period_inputs(startMonth, endMonth, startDate, endDate)
    result = _build_db_dashboard(
        db=db,
        start_date=resolved_start_date,
        end_date=resolved_end_date,
        category=category,
        company=company,
        product_name=productName,
    )
    excel_file = create_excel(result["company_rank"], result["chart_data"])
    filename = f"dashboard_db_{resolved_start_date}_{resolved_end_date}.xlsx"
    return StreamingResponse(
        excel_file,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/dashboard/market-share", response_model=DashboardResponse)
def get_market_share(
    start_month: str = Query(..., description="조회 시작월 (YYYY-MM)"),
    end_month: str = Query(..., description="조회 종료월 (YYYY-MM)"),
    item_code: str = Query("", description="품목코드"),
    manufacturer_name: str = Query("", description="제조사명"),
    top_n: int = Query(10, ge=1, le=100, description="상위 제조사 건수"),
    use_dummy: bool = Query(True, description="더미 데이터 사용 여부"),
    db: Session = Depends(get_db),
):
    _validate_month_range(start_month, end_month)
    return _build_result(db, start_month, end_month, item_code, manufacturer_name, top_n, use_dummy)


@router.get("/dashboard/market-share/excel")
def download_market_share_excel(
    start_month: str = Query(...),
    end_month: str = Query(...),
    item_code: str = Query(""),
    manufacturer_name: str = Query(""),
    top_n: int = Query(10, ge=1, le=100),
    use_dummy: bool = Query(True),
    db: Session = Depends(get_db),
):
    _validate_month_range(start_month, end_month)
    result = _build_result(db, start_month, end_month, item_code, manufacturer_name, top_n, use_dummy)

    excel_file = create_excel(result["table_rows"], result["chart_rows"])
    filename = f"market_share_{start_month}_{end_month}.xlsx"
    return StreamingResponse(
        excel_file,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
