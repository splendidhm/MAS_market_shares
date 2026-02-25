from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

import requests

from app.core.config import settings


class OpenApiError(Exception):
    pass


class OpenApiAuthError(OpenApiError):
    pass


@dataclass
class ApiQueryParams:
    start_month: str
    end_month: str
    item_code: str
    manufacturer_name: str


class ProcurementApiClient:
    def __init__(self):
        self.base_url = settings.open_api_base_url
        self.service_key = settings.open_api_service_key
        self.timeout = settings.api_timeout_seconds

    def fetch(self, params: ApiQueryParams, use_dummy: bool = True) -> List[Dict[str, Any]]:
        if use_dummy:
            return self._dummy_rows(params)
        return self._fetch_real(params)

    def _fetch_real(self, params: ApiQueryParams) -> List[Dict[str, Any]]:
        if not self.base_url:
            raise OpenApiError("OPEN_API_BASE_URL 설정이 필요합니다.")
        if not self.service_key:
            raise OpenApiAuthError("서비스키가 없습니다. .env 파일을 확인하세요.")

        query_params = {
            "serviceKey": self.service_key,
            "startMonth": params.start_month,
            "endMonth": params.end_month,
            "itemCode": params.item_code,
            "manufacturerName": params.manufacturer_name,
            "type": "json",
        }

        try:
            response = requests.get(self.base_url, params=query_params, timeout=self.timeout)
        except requests.RequestException as exc:
            raise OpenApiError(f"Open API 호출 실패: {exc}") from exc

        if response.status_code in (401, 403):
            raise OpenApiAuthError("인증키가 유효하지 않거나 만료되었습니다.")
        if response.status_code >= 400:
            raise OpenApiError(f"Open API 오류 응답: HTTP {response.status_code}")

        payload = response.json()

        # 조달청 API 응답 형식이 다양한 경우를 대비하여 여러 경로를 지원
        if isinstance(payload, dict):
            rows = payload.get("data") or payload.get("items") or payload.get("response", {}).get("body", {}).get("items", [])
        else:
            rows = payload

        if not rows:
            return []
        if not isinstance(rows, list):
            raise OpenApiError("예상하지 못한 JSON 구조입니다.")

        return [self._normalize_row(row) for row in rows]

    @staticmethod
    def _normalize_row(row: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "period_month": str(row.get("period_month") or row.get("month") or ""),
            "category_main": str(row.get("category_main") or row.get("category1") or ""),
            "category_sub": str(row.get("category_sub") or row.get("category2") or ""),
            "manufacturer": str(row.get("manufacturer") or row.get("maker") or ""),
            "item_code": str(row.get("item_code") or row.get("itemCode") or ""),
            "item_name": str(row.get("item_name") or row.get("itemName") or ""),
            "spec": str(row.get("spec") or row.get("standard") or ""),
            "quantity": float(row.get("quantity") or 0),
            "amount": float(row.get("amount") or row.get("supplyAmount") or 0),
            "region": str(row.get("region") or ""),
            "military_branch": str(row.get("military_branch") or ""),
            "contract_no": str(row.get("contract_no") or ""),
        }

    @staticmethod
    def _dummy_rows(params: ApiQueryParams) -> List[Dict[str, Any]]:
        manufacturer_filter = params.manufacturer_name.strip().lower()
        base_rows = [
            ["2026-01", "식품", "즉석식품", "A푸드", "즉석밥", "210g", 12000, 144000000, "F001"],
            ["2026-01", "식품", "즉석식품", "B푸드", "즉석밥", "210g", 9000, 105000000, "F001"],
            ["2026-01", "식품", "면류", "C밀", "컵라면", "105g", 15000, 90000000, "F002"],
            ["2026-01", "식품", "음료", "D음료", "이온음료", "500ml", 11000, 77000000, "F003"],
            ["2026-01", "식품", "통조림", "E캔", "참치캔", "150g", 8000, 68000000, "F004"],
            ["2026-02", "식품", "즉석식품", "A푸드", "즉석밥", "210g", 13000, 156000000, "F001"],
            ["2026-02", "식품", "즉석식품", "B푸드", "즉석밥", "210g", 8900, 101460000, "F001"],
            ["2026-02", "식품", "면류", "C밀", "컵라면", "105g", 16400, 98400000, "F002"],
            ["2026-02", "식품", "음료", "D음료", "이온음료", "500ml", 10800, 75600000, "F003"],
            ["2026-02", "식품", "통조림", "E캔", "참치캔", "150g", 8200, 69700000, "F004"],
        ]

        rows = []
        for month, c1, c2, mfr, item, spec, qty, amt, item_code in base_rows:
            if params.item_code and params.item_code != item_code:
                continue
            if manufacturer_filter and manufacturer_filter not in mfr.lower():
                continue
            rows.append(
                {
                    "period_month": month,
                    "category_main": c1,
                    "category_sub": c2,
                    "manufacturer": mfr,
                    "item_code": item_code,
                    "item_name": item,
                    "spec": spec,
                    "quantity": float(qty),
                    "amount": float(amt),
                    "region": "전국",
                    "military_branch": "",
                    "contract_no": "",
                }
            )
        return rows
