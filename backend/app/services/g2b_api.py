from __future__ import annotations

import calendar
import os
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import requests
from dotenv import load_dotenv

from app.core.config import settings


ROOT_DIR = Path(__file__).resolve().parents[3]
# 운영 시 .env 위치가 달라도 fallback 되도록 후보 경로를 여러 개 둔다.
ANALYZER_ENV_PATH = ROOT_DIR / "food_openapi_analyzer" / ".env"
ROOT_ENV_PATH = ROOT_DIR / ".env"
BACKEND_ENV_PATH = ROOT_DIR / "backend" / ".env"


class G2BApiError(Exception):
    pass


class G2BAuthError(G2BApiError):
    pass


class G2BRateLimitError(G2BApiError):
    pass


class G2BApiClient:
    def __init__(self):
        # 여러 실행 경로를 고려해 .env 후보를 순서대로 로드
        load_dotenv(ROOT_ENV_PATH, override=False)
        load_dotenv(BACKEND_ENV_PATH, override=False)
        load_dotenv(ANALYZER_ENV_PATH, override=False)

        # 우선순위: G2B_SERVICE_KEY > SERVICE_KEY > settings.open_api_service_key
        # 키명을 바꾸고 싶으면 이 블록만 수정하면 된다.
        self.service_key = (
            os.getenv("G2B_SERVICE_KEY", "").strip()
            or os.getenv("SERVICE_KEY", "").strip()
            or settings.open_api_service_key
        )
        # 우선순위: G2B_BASE_URL > BASE_URL > settings.open_api_base_url
        raw_base_url = (
            os.getenv("G2B_BASE_URL", "").strip()
            or os.getenv("BASE_URL", "").strip()
            or settings.open_api_base_url
            or "https://apis.data.go.kr/1230000/at/ShoppingMallPrdctInfoService/getDlvrReqDtlInfoList"
        )
        # 오퍼레이션명을 바꾸는 경우 .env 의 G2B_OPERATION 또는 OPERATION 수정
        operation = os.getenv("G2B_OPERATION", "").strip() or os.getenv("OPERATION", "").strip() or "getDlvrReqDtlInfoList"
        self.base_url = self._normalize_endpoint(raw_base_url, operation)
        # getDlvrReqDtlInfoList에서 필수인 조회구분 값 (기본 1)
        self.inqry_div = os.getenv("G2B_INQRY_DIV", "").strip() or os.getenv("INQRY_DIV", "").strip() or "1"
        # 요청 간격(초). 429 방지를 위해 1.5초 이상 권장.
        self.request_sleep_seconds = float(
            os.getenv("G2B_REQUEST_SLEEP_SECONDS", "").strip()
            or os.getenv("REQUEST_SLEEP_SECONDS", "").strip()
            or "1.5"
        )
        # 본 오퍼레이션은 페이지당 건수가 작아 상한을 두지 않으면 조회 시간이 과도해질 수 있다.
        self.max_pages = int(os.getenv("G2B_MAX_PAGES", "").strip() or "10")
        self.timeout = settings.api_timeout_seconds

    @staticmethod
    def _normalize_endpoint(base_url: str, operation: str) -> str:
        base = base_url.rstrip("/")
        if base.endswith(operation):
            return base
        # 서비스 루트 URL이 오면 operation 을 자동으로 붙인다.
        if base.endswith("Service") or "ShoppingMallPrdctInfoService" in base or "PubPrcrmntStatInfoService" in base:
            return f"{base}/{operation}"
        return base

    def fetch_sales_data(
        self,
        start_month: str,
        end_month: str,
        category_filter: str = "",
        request_guard: Optional[Callable[[], None]] = None,
        request_record: Optional[Callable[[], None]] = None,
    ) -> List[Dict[str, Any]]:
        if not self.service_key:
            raise G2BAuthError("G2B_SERVICE_KEY(또는 SERVICE_KEY)가 설정되지 않았습니다.")

        all_items: List[Dict[str, Any]] = []
        page_no = 1
        # 조달청 API 트래픽 제한을 고려해 기본 페이지 크기를 1000으로 사용
        num_of_rows = 1000

        while True:
            if page_no > self.max_pages:
                break
            inqry_bgn_date, inqry_end_date = self._to_inqry_dates(start_month, end_month)
            params = {
                "serviceKey": self.service_key,
                "pageNo": page_no,
                "numOfRows": num_of_rows,
                "type": "json",
                # getDlvrReqDtlInfoList 필수 파라미터
                "inqryDiv": self.inqry_div,
                "inqryBgnDate": inqry_bgn_date,
                "inqryEndDate": inqry_end_date,
            }
            # 품목분류코드(숫자)가 들어오면 서버 측 필터를 우선 적용해 호출량을 줄인다.
            if category_filter and category_filter.strip().isdigit():
                params["prdctClsfcNo"] = category_filter.strip()

            response = None
            backoff_seconds = [5, 10, 20]
            for retry in range(4):
                try:
                    if request_guard:
                        request_guard()
                    response = requests.get(self.base_url, params=params, timeout=self.timeout)
                    if request_record:
                        request_record()
                except requests.RequestException as exc:
                    if retry == 3:
                        raise G2BApiError(f"조달청 OpenAPI 호출 실패: {exc}") from exc
                    time.sleep(1.0 * (retry + 1))
                    continue
                if response.status_code != 429:
                    break
                if retry == 3:
                    raise G2BApiError("조달청 OpenAPI HTTP 오류: 429 (요청 제한 초과)")
                time.sleep(backoff_seconds[retry])

            if response is None:
                raise G2BApiError("조달청 OpenAPI 호출 실패: 빈 응답")

            if response.status_code in (401, 403):
                raise G2BAuthError("인증키가 유효하지 않거나 활용신청이 승인되지 않았습니다.")
            if response.status_code >= 400:
                raise G2BApiError(f"조달청 OpenAPI HTTP 오류: {response.status_code}")

            payload = response.json()
            header = payload.get("response", {}).get("header", {})
            result_code = str(header.get("resultCode", ""))
            result_msg = str(header.get("resultMsg", ""))

            if result_code and result_code != "00":
                if "SERVICE KEY" in result_msg.upper() or result_code in {"30", "22"}:
                    raise G2BAuthError(f"인증키 오류: {result_msg}")
                raise G2BApiError(f"조달청 OpenAPI 오류({result_code}): {result_msg}")

            body = payload.get("response", {}).get("body", {})
            total_count = int(body.get("totalCount", 0) or 0)
            items = body.get("items", [])
            if isinstance(items, dict):
                items = items.get("item", [])
            if not isinstance(items, list):
                items = []

            if total_count <= 0:
                break

            all_items.extend(items)

            if not items or len(all_items) >= total_count:
                break

            page_no += 1
            time.sleep(self.request_sleep_seconds)

        return all_items

    @staticmethod
    def _to_inqry_dates(start_month: str, end_month: str) -> tuple[str, str]:
        # YYYYMMDD가 들어오면 그대로 사용, YYYYMM이면 월 경계일로 변환
        if len(start_month) == 8 and len(end_month) == 8:
            return start_month, end_month
        s_year = int(start_month[:4])
        s_month = int(start_month[4:6])
        e_year = int(end_month[:4])
        e_month = int(end_month[4:6])
        last_day = calendar.monthrange(e_year, e_month)[1]
        return f"{s_year:04d}{s_month:02d}01", f"{e_year:04d}{e_month:02d}{last_day:02d}"
