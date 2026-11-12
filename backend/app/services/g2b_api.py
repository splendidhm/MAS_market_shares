from __future__ import annotations

import os
from pathlib import Path

import requests
from dotenv import load_dotenv

from app.core.config import settings


ROOT_DIR = Path(__file__).resolve().parents[3]
SHOPPING_SERVICE = "https://apis.data.go.kr/1230000/at/ShoppingMallPrdctInfoService"
REGISTRATION_OPERATION = "getShoppingMallPrdctInfoList"
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
    def __init__(self, *, registration=False):
        # 여러 실행 경로를 고려해 .env 후보를 순서대로 로드
        load_dotenv(ROOT_ENV_PATH, override=False)
        load_dotenv(BACKEND_ENV_PATH, override=False)
        load_dotenv(ANALYZER_ENV_PATH, override=False)

        # 우선순위: G2B_SERVICE_KEY > SERVICE_KEY > settings.open_api_service_key
        # 키명을 바꾸고 싶으면 이 블록만 수정하면 된다.
        self.service_key = (
            os.getenv("G2B_SERVICE_KEY", "").strip()
            or os.getenv("SERVICE_KEY", "").strip()
            or os.getenv("OPEN_API_SERVICE_KEY", "").strip()
            or settings.open_api_service_key
        )
        # 우선순위: G2B_BASE_URL > BASE_URL > settings.open_api_base_url
        raw_base_url = (
            os.getenv("G2B_BASE_URL", "").strip()
            or os.getenv("BASE_URL", "").strip()
            or settings.open_api_base_url
            or f"{SHOPPING_SERVICE}/getDlvrReqDtlInfoList"
        )
        # 오퍼레이션명을 바꾸는 경우 .env 의 G2B_OPERATION 또는 OPERATION 수정
        operation = os.getenv("G2B_OPERATION", "").strip() or os.getenv("OPERATION", "").strip() or "getDlvrReqDtlInfoList"
        self.base_url = (f"{SHOPPING_SERVICE}/{REGISTRATION_OPERATION}" if registration
                         else self._normalize_endpoint(raw_base_url, operation))
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

    def fetch_page(self, start, end, page, field="", keyword=""):
        if not self.service_key:
            raise G2BAuthError("조달청 서비스키가 필요합니다.")
        params = dict(serviceKey=self.service_key, type="json", inqryDiv="1",
                      inqryBgnDate=start, inqryEndDate=end, pageNo=page, numOfRows=999)
        if field:
            params[field] = keyword
        try:
            response = requests.get(self.base_url, params=params, timeout=(10, max(60, self.timeout)))
            if response.status_code in (401, 403):
                raise G2BAuthError("조달청 인증키 또는 활용 승인을 확인해주세요.")
            if response.status_code == 429:
                raise G2BRateLimitError("조달청 호출 한도에 도달했습니다. 이후 같은 조건으로 이어받을 수 있습니다.")
            response.raise_for_status()
            payload = response.json()["response"]
            header = payload["header"]
            code = str(header["resultCode"])
            if code in {"20", "30", "31", "32"}:
                raise G2BAuthError("조달청 인증키 또는 활용 승인을 확인해주세요.")
            if code == "22":
                raise G2BRateLimitError("조달청 호출 한도에 도달했습니다. 이후 같은 조건으로 이어받을 수 있습니다.")
            if code != "00":
                raise G2BApiError(f"조달청 응답 {header['resultCode']}: {header.get('resultMsg', '')}")
            body = payload["body"]
            total, size, number = (int(body[k]) for k in ("totalCount", "numOfRows", "pageNo"))
            items = body.get("items") or []
            if isinstance(items, dict):
                items = items.get("item", [])
            if isinstance(items, dict):
                items = [items]
            if (not isinstance(items, list) or not all(isinstance(item, dict) for item in items)
                    or number != page or total < 0 or size != params["numOfRows"]
                    or len(items) != min(size, max(0, total - (page - 1) * size))):
                raise G2BApiError("조달청 페이지 건수가 일치하지 않습니다. 같은 페이지에서 재시도해주세요.")
            return total, size, items
        except (requests.RequestException, KeyError, TypeError, ValueError) as exc:
            raise G2BApiError("조달청 응답을 읽지 못했습니다. 같은 조건으로 재시도해주세요.") from None
