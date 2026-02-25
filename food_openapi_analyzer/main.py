import os
import re
from typing import List

import pandas as pd
from dotenv import load_dotenv

from api_client import ApiAuthError, ApiClientError, ProcurementApiClient
from data_processor import aggregate_dataframes, build_raw_dataframe
from export_excel import build_output_filename, export_to_excel
from food_filter import (
    classify_rows_by_food_keywords,
    build_keyword_matched_code_map,
    iter_active_food_categories,
    load_food_category_codes,
)


def validate_yyyymm(value: str) -> bool:
    return bool(re.fullmatch(r"\d{6}", value))


def prompt_period() -> (str, str):
    while True:
        start_yyyymm = input("조회 시작년월(YYYYMM): ").strip()
        end_yyyymm = input("조회 종료년월(YYYYMM): ").strip()

        if not validate_yyyymm(start_yyyymm) or not validate_yyyymm(end_yyyymm):
            print("형식 오류: YYYYMM 6자리로 입력해주세요.")
            continue
        if start_yyyymm > end_yyyymm:
            print("입력 오류: 시작년월은 종료년월보다 작거나 같아야 합니다.")
            continue
        return start_yyyymm, end_yyyymm


def main():
    # 운영 시 .env 에서 SERVICE_KEY/BASE_URL/OPERATION 값을 우선 로드
    load_dotenv()

    # ===== 수동 설정 포인트 (키/엔드포인트/속도) =====
    service_key = os.getenv("SERVICE_KEY", "").strip()
    base_url = os.getenv(
        "BASE_URL", "https://apis.data.go.kr/1230000/at/ShoppingMallPrdctInfoService"
    ).strip()
    operation = os.getenv("OPERATION", "getDlvrReqDtlInfoList").strip()
    inqry_div = os.getenv("INQRY_DIV", "1").strip()
    # API 트래픽 제한 대응용 sleep (요청 간격)
    sleep_seconds = float(os.getenv("REQUEST_SLEEP_SECONDS", "0.2"))
    max_pages = int(os.getenv("MAX_PAGES", "300"))

    if not service_key:
        raise ValueError("SERVICE_KEY가 없습니다. .env 파일에 SERVICE_KEY를 설정해주세요.")

    start_yyyymm, end_yyyymm = prompt_period()

    current_dir = os.path.dirname(os.path.abspath(__file__))
    # 식품 카테고리-품목코드 매핑 파일 (가장 먼저 수동 보완할 파일)
    config_path = os.path.join(current_dir, "config", "food_category_codes.json")
    category_codes = load_food_category_codes(config_path)

    # 조달청 API 호출 인스턴스
    client = ProcurementApiClient(
        service_key=service_key,
        base_url=base_url,
        operation=operation,
        inqry_div=inqry_div,
        sleep_seconds=sleep_seconds,
        max_pages=max_pages,
    )

    # 코드 미입력 카테고리가 있을 경우, 기간 전체 조회 1회로 코드 자동 매핑 시도
    seed_rows = []
    if any(not code for code in category_codes.values()):
        print("[안내] 일부 식품코드가 비어 있어 자동 코드 탐색을 시도합니다...")
        try:
            seed_rows = client.fetch_by_product_code(start_yyyymm, end_yyyymm, product_code=None)
            category_codes = build_keyword_matched_code_map(category_codes, seed_rows)
        except ApiClientError as exc:
            print(f"[경고] 자동 코드 탐색 실패: {exc}")

    try:
        active_categories = iter_active_food_categories(category_codes)
    except ValueError as exc:
        # 품목코드가 모두 비어있으면 키워드 기반 분류 모드로 fallback
        if not seed_rows:
            print(f"[종료] {exc}")
            return
        print("[안내] 품목코드가 없어 키워드 기반 식품 분류 모드로 진행합니다.")
        matched_rows = classify_rows_by_food_keywords(category_codes, seed_rows)
        if not matched_rows:
            print("[종료] 키워드 매칭된 식품 데이터가 없습니다.")
            return

        grouped_rows = {}
        for category_name, row in matched_rows:
            grouped_rows.setdefault(category_name, []).append(row)

        raw_frames: List[pd.DataFrame] = []
        for category_name, rows in grouped_rows.items():
            df_category = build_raw_dataframe(rows, category_name=category_name)
            if not df_category.empty:
                raw_frames.append(df_category)

        if not raw_frames:
            print("[종료] 키워드 기반 분류 결과가 비어있습니다.")
            return

        raw_df = pd.concat(raw_frames, ignore_index=True)
        monthly_summary_df, item_monthly_df, pivot_df, item_total_df = aggregate_dataframes(raw_df)

        print("\n===== 월별 합계 =====")
        print(monthly_summary_df.to_string(index=False))
        print("\n===== 품목별 합계 =====")
        print(item_total_df.to_string(index=False))

        output_name = build_output_filename(end_yyyymm)
        output_path = os.path.join(os.getcwd(), output_name)
        export_to_excel(
            file_path=output_path,
            raw_df=raw_df,
            monthly_summary_df=monthly_summary_df,
            pivot_df=pivot_df,
            item_monthly_df=item_monthly_df,
            item_total_df=item_total_df,
        )
        print(f"\n엑셀 저장 완료: {output_path}")
        return

    print("[조회] 기간 전체 원천데이터를 1회 수집합니다...")
    try:
        all_rows = client.fetch_by_product_code(start_yyyymm, end_yyyymm, product_code=None)
    except ApiAuthError as exc:
        raise RuntimeError(f"인증 오류: {exc}") from exc
    except ApiClientError as exc:
        raise RuntimeError(f"원천데이터 조회 실패: {exc}") from exc

    raw_frames: List[pd.DataFrame] = []
    for category_name, product_code in active_categories:
        rows = [
            row
            for row in all_rows
            if str(row.get("prdctClsfcNo", "") or "").strip().startswith(str(product_code))
        ]
        if not rows:
            print(f"[정보] {category_name} ({product_code}): 데이터 없음")
            continue
        print(f"[매핑] {category_name} ({product_code}) -> {len(rows)}건")
        df_category = build_raw_dataframe(rows, category_name=category_name)
        if not df_category.empty:
            raw_frames.append(df_category)

    if not raw_frames:
        print("조회된 식품류 데이터가 없습니다.")
        return

    raw_df = pd.concat(raw_frames, ignore_index=True)
    monthly_summary_df, item_monthly_df, pivot_df, item_total_df = aggregate_dataframes(raw_df)

    print("\n===== 월별 합계 =====")
    print(monthly_summary_df.to_string(index=False))
    print("\n===== 품목별 합계 =====")
    print(item_total_df.to_string(index=False))

    output_name = build_output_filename(end_yyyymm)
    output_path = os.path.join(os.getcwd(), output_name)
    export_to_excel(
        file_path=output_path,
        raw_df=raw_df,
        monthly_summary_df=monthly_summary_df,
        pivot_df=pivot_df,
        item_monthly_df=item_monthly_df,
        item_total_df=item_total_df,
    )
    print(f"\n엑셀 저장 완료: {output_path}")


if __name__ == "__main__":
    main()
