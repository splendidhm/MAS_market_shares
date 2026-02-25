import json
import os
from typing import Dict, Iterable, List, Tuple


def _row_product_text(row: Dict) -> str:
    # 오퍼레이션마다 품목명 컬럼이 달라질 수 있어 후보를 순서대로 합친다.
    return " ".join(
        [
            str(row.get("prdctIdntNoNm", "") or ""),
            str(row.get("prdctNm", "") or ""),
            str(row.get("prdctClsfcNoNm", "") or ""),
            str(row.get("dtilPrdctClsfcNoNm", "") or ""),
        ]
    )


def _row_product_code(row: Dict) -> str:
    # 최신 오퍼레이션은 prdctClsfcNo를 우선 사용한다.
    return str(row.get("prdctClsfcNo", "") or row.get("prdctClCd", "") or row.get("prdctIdntNo", "")).strip()


def _category_keywords(category_name: str) -> List[str]:
    # 카테고리명과 자주 쓰는 동의어를 같이 매칭해 누락을 줄인다.
    alias_map = {
        "국탕류": ["국", "탕", "찌개"],
        "장류": ["장", "된장", "간장", "고추장"],
        "혼합장": ["혼합장", "쌈장"],
        "소시지류": ["소시지", "햄"],
        "수산물가공품": ["수산", "어묵", "참치"],
        "식육가공품": ["식육", "육가공", "햄", "소시지"],
        "축산가공품": ["축산", "육가공", "햄", "소시지"],
        "조미김": ["조미김", "김"],
        "면류": ["면", "국수", "라면", "우동"],
        "떡": ["떡", "떡볶이"],
        "빵류": ["빵", "식빵", "베이글"],
        "과자류": ["과자", "비스킷", "쿠키"],
        "발효유": ["발효유", "요구르트", "요거트"],
    }
    return [category_name] + alias_map.get(category_name, [])


def load_food_category_codes(config_path: str) -> Dict[str, str]:
    """
    식품 카테고리-품목코드 매핑 로드.
    코드가 비어있으면 자동탐색 후보로 유지한다.
    """
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"식품코드 설정 파일이 없습니다: {config_path}")

    with open(config_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, dict):
        raise ValueError("식품코드 설정 파일 형식이 올바르지 않습니다.")
    return {str(k): str(v or "").strip() for k, v in data.items()}


def build_keyword_matched_code_map(
    category_codes: Dict[str, str], seed_rows: Iterable[Dict]
) -> Dict[str, str]:
    """
    코드가 비어있는 카테고리에 대해, 응답의 품목명/품목코드 필드로 자동 매핑 시도.
    """
    resolved = dict(category_codes)
    unresolved = {name for name, code in resolved.items() if not code}
    if not unresolved:
        return resolved

    for row in seed_rows:
        product_text = _row_product_text(row)
        product_code = _row_product_code(row)
        if not product_code:
            continue
        for cat_name in list(unresolved):
            keywords = _category_keywords(cat_name)
            if any(keyword and keyword in product_text for keyword in keywords):
                resolved[cat_name] = product_code
                unresolved.remove(cat_name)
                if not unresolved:
                    return resolved
    return resolved


def iter_active_food_categories(category_codes: Dict[str, str]) -> List[Tuple[str, str]]:
    active = [(name, code) for name, code in category_codes.items() if code]
    if not active:
        raise ValueError(
            "식품 품목코드가 비어있습니다. "
            "config/food_category_codes.json 파일에 품목코드를 입력해주세요."
        )
    return active


def classify_rows_by_food_keywords(
    category_codes: Dict[str, str], rows: Iterable[Dict]
) -> List[Tuple[str, Dict]]:
    """
    품목코드가 없을 때, prdctNm 문자열 기준으로 식품 카테고리를 분류한다.
    """
    category_names = list(category_codes.keys())
    matched: List[Tuple[str, Dict]] = []
    for row in rows:
        product_text = _row_product_text(row)
        for category_name in category_names:
            keywords = _category_keywords(category_name)
            if any(keyword and keyword in product_text for keyword in keywords):
                matched.append((category_name, row))
                break
    return matched
