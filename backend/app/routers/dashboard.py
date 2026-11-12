from __future__ import annotations

import calendar
from datetime import datetime
import os
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas import DashboardResponse
from app.services.data_processor import DataProcessor
from app.services.excel_exporter import create_excel, create_food_excel, create_registration_excel
from app.services.food_report import DELIVERIES, REGISTRATIONS, report, sync_step
from app.services.registrations import available_period, registration_report
from app.services.quota_service import get_today_call_count

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
        try:
            return _yyyymm_to_date_range(start_month, end_month)
        except (ValueError, IndexError):
            raise HTTPException(400, "유효한 월을 입력해주세요.")
    raise HTTPException(status_code=400, detail="startDate/endDate 또는 startMonth/endMonth를 함께 전달해야 합니다.")


def _build_result(
    db: Session,
    start_month: str,
    end_month: str,
    item_code: str,
    manufacturer_name: str,
    top_n: int,
    use_dummy: bool,
) -> Dict[str, Any]:
    start, end = _yyyymm_to_date_range(start_month.replace("-", ""), end_month.replace("-", ""))
    rows = []

    def add_row(row):
        if item_code and not any(str(row.get(k) or "").startswith(item_code)
                                 for k in ("prdctClsfcNo","dtilPrdctClsfcNo","prdctIdntNo")):
            return
        rows.append(dict(period_month=row["dlvrReqRcptDate"][:7],
                         manufacturer=row.get("corpNm") or "업체명 미제공",
                         category_main=row.get("prdctClsfcNoNm") or "",
                         category_sub=row.get("dtilPrdctClsfcNoNm") or "",
                         item_name=row.get("prdctIdntNoNm") or "", spec=row.get("prdctUnit") or "",
                         quantity=float(row.get("incdecQty") or row.get("prdctQty") or 0),
                         amount=float(row.get("incdecAmt") or row.get("prdctAmt") or 0)))

    result = report(db, start, end, "", manufacturer_name, "", on_record=add_row)
    if not result["complete"]:
        raise HTTPException(409, "선택 기간의 전체 식품 DB 동기화가 필요합니다.")
    table, chart, total = DataProcessor().build_dashboard(rows, start_month, end_month, top_n)
    return dict(table_rows=table, chart_rows=chart, total_amount=total, cache_hit=True)


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
    return report(db, resolved_start_date, resolved_end_date, category, company, productName)


@router.post("/dashboard/sync")
def sync_dashboard_cache(
    startMonth: Optional[str] = Query(None, pattern=r"^\d{6}$", description="동기화 시작월 (YYYYMM)"),
    endMonth: Optional[str] = Query(None, pattern=r"^\d{6}$", description="동기화 종료월 (YYYYMM)"),
    startDate: Optional[str] = Query(None, pattern=r"^\d{8}$", description="동기화 시작일 (YYYYMMDD)"),
    endDate: Optional[str] = Query(None, pattern=r"^\d{8}$", description="동기화 종료일 (YYYYMMDD)"),
    category: str = Query("", max_length=100),
    step: bool = Query(False, description="한 페이지 처리 후 진행 상태 반환"),
    force: bool = Query(False),
    db: Session = Depends(get_db),
):
    start, end = _resolve_period_inputs(startMonth, endMonth, startDate, endDate)
    return _sync_collection(db, DELIVERIES, start, end, category, step, force)


def _sync_collection(db, source, start, end, category, step, force):
    state = sync_step(db, start, end, category, DAILY_CALL_LIMIT, refresh=force, source=source)
    while not step and not state["complete"]:
        state = sync_step(db, start, end, category, DAILY_CALL_LIMIT, source=source)
    return state


@router.post("/registrations/sync")
def sync_registrations(
    startDate: str = Query(..., pattern=r"^\d{8}$"),
    endDate: str = Query(..., pattern=r"^\d{8}$"),
    category: str = Query("", max_length=100),
    step: bool = False,
    force: bool = False,
    db: Session = Depends(get_db),
):
    start, end = available_period(startDate, endDate)
    return _sync_collection(db, REGISTRATIONS, start, end, category, step, force)


@router.get("/registrations")
def get_registrations(
    startDate: str = Query(..., pattern=r"^\d{8}$"),
    endDate: str = Query(..., pattern=r"^\d{8}$"),
    category: str = Query("", max_length=100),
    company: str = "",
    productName: str = "",
    page: int = Query(1, ge=1),
    pageSize: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    start, end = available_period(startDate, endDate)
    return registration_report(db, start, end, category, company, productName, page, pageSize)


@router.get("/registrations/excel")
def download_registrations_excel(
    startDate: str = Query(..., pattern=r"^\d{8}$"),
    endDate: str = Query(..., pattern=r"^\d{8}$"),
    category: str = Query("", max_length=100),
    company: str = "",
    productName: str = "",
    db: Session = Depends(get_db),
):
    start, end = available_period(startDate, endDate)
    excel_file = create_registration_excel(db, start, end, category, company, productName)

    def chunks():
        with excel_file:
            while chunk := excel_file.read(65536):
                yield chunk

    filename = f"food_registrations_{start}_{end}.xlsx"
    return StreamingResponse(
        chunks(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


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
    excel_file = create_food_excel(db, resolved_start_date, resolved_end_date, category, company, productName)

    def chunks():
        with excel_file:
            while chunk := excel_file.read(65536):
                yield chunk
    filename = f"food_{resolved_start_date}_{resolved_end_date}.xlsx"
    return StreamingResponse(
        chunks(),
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
    use_dummy: bool = Query(False, description="더미 데이터 사용 여부"),
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
    use_dummy: bool = Query(False),
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
