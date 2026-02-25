import json
import calendar
import time
from typing import Dict, List, Optional

import requests


class ApiClientError(Exception):
    """OpenAPI 호출 중 발생한 일반 오류."""


class ApiAuthError(ApiClientError):
    """인증키 만료/오류."""


class ProcurementApiClient:
    def __init__(
        self,
        service_key: str,
        base_url: str,
        operation: str,
        inqry_div: str = "1",
        sleep_seconds: float = 1.5,
        timeout_seconds: int = 20,
        max_pages: int = 10,
    ):
        # 수동 설정 포인트: 키/엔드포인트/요청 간격/타임아웃
        self.service_key = service_key
        self.endpoint = f"{base_url.rstrip('/')}/{operation}"
        self.inqry_div = inqry_div
        self.sleep_seconds = sleep_seconds
        self.timeout_seconds = timeout_seconds
        self.max_pages = max_pages

    def fetch_by_product_code(
        self,
        start_yyyymm: str,
        end_yyyymm: str,
        product_code: Optional[str] = None,
    ) -> List[Dict]:
        """
        한 품목코드(또는 전체)에 대해 페이지네이션으로 전체 데이터를 수집한다.
        """
        all_rows: List[Dict] = []
        page_no = 1
        # 대량 데이터 누락 방지를 위해 페이지 크기를 크게 설정
        num_of_rows = 1000
        inqry_bgn_date, inqry_end_date = self._to_inqry_dates(start_yyyymm, end_yyyymm)

        while True:
            if page_no > self.max_pages:
                break
            params = {
                # 종합쇼핑몰 납품요구상세 조회(getDlvrReqDtlInfoList) 파라미터
                "serviceKey": self.service_key,
                "pageNo": page_no,
                "numOfRows": num_of_rows,
                "type": "json",
                "inqryDiv": self.inqry_div,
                "inqryBgnDate": inqry_bgn_date,
                "inqryEndDate": inqry_end_date,
            }

            payload = self._safe_get_json(params)
            page_rows, total_count = self._extract_items(payload)
            if total_count <= 0:
                break
            if not page_rows:
                break

            if product_code:
                prefix = str(product_code).strip()
                page_rows = [
                    row
                    for row in page_rows
                    if str(row.get("prdctClsfcNo", "") or "").strip().startswith(prefix)
                ]
                if not page_rows:
                    page_no += 1
                    time.sleep(self.sleep_seconds)
                    continue

            all_rows.extend(page_rows)

            if len(all_rows) >= total_count:
                break

            page_no += 1
            time.sleep(self.sleep_seconds)

        return all_rows

    @staticmethod
    def _to_inqry_dates(start_yyyymm: str, end_yyyymm: str) -> tuple[str, str]:
        s_year = int(start_yyyymm[:4])
        s_month = int(start_yyyymm[4:6])
        e_year = int(end_yyyymm[:4])
        e_month = int(end_yyyymm[4:6])
        last_day = calendar.monthrange(e_year, e_month)[1]
        return f"{s_year:04d}{s_month:02d}01", f"{e_year:04d}{e_month:02d}{last_day:02d}"

    def _safe_get_json(self, params: Dict) -> Dict:
        response = None
        backoff_seconds = [5, 10, 20]
        for retry in range(4):
            try:
                response = requests.get(self.endpoint, params=params, timeout=self.timeout_seconds)
            except requests.RequestException as exc:
                if retry == 3:
                    raise ApiClientError(f"API 호출 실패: {exc}") from exc
                time.sleep(self.sleep_seconds * (retry + 1))
                continue
            if response.status_code != 429:
                break
            if retry == 3:
                raise ApiClientError("HTTP 오류: 429 (요청 제한 초과)")
            time.sleep(backoff_seconds[retry])

        if response is None:
            raise ApiClientError("API 호출 실패: 빈 응답")

        if response.status_code != 200:
            raise ApiClientError(f"HTTP 오류: {response.status_code}")

        try:
            payload = response.json()
        except json.JSONDecodeError as exc:
            raise ApiClientError(f"JSON 파싱 실패: {exc}") from exc

        # 공공데이터 표준 응답 코드 검사
        header = payload.get("response", {}).get("header", {})
        result_code = str(header.get("resultCode", ""))
        result_msg = str(header.get("resultMsg", ""))
        if result_code and result_code != "00":
            if "SERVICE KEY" in result_msg.upper() or result_code in {"22", "30"}:
                raise ApiAuthError(f"인증키 오류/만료: {result_msg}")
            raise ApiClientError(f"API 응답 오류({result_code}): {result_msg}")

        return payload

    @staticmethod
    def _extract_items(payload: Dict) -> (List[Dict], int):
        body = payload.get("response", {}).get("body", {})
        total_count = int(body.get("totalCount", 0) or 0)
        items = body.get("items", [])

        if isinstance(items, dict):
            # 공공데이터 API는 items가 dict(item=[]) 구조인 경우가 있다.
            items = items.get("item", [])
        if isinstance(items, list):
            rows = items
        else:
            rows = []

        return rows, total_count
