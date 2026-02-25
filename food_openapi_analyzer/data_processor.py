from typing import Dict, List, Tuple

import pandas as pd


def _extract_year_month(row: Dict) -> Tuple[str, str]:
    # 신 오퍼레이션: dlvrReqRcptDate(YYYY-MM-DD) 우선, 구 오퍼레이션은 bssYear/bssMnth fallback
    dlvr_date = str(row.get("dlvrReqRcptDate", "") or "").strip()
    if len(dlvr_date) >= 7 and "-" in dlvr_date:
        year = dlvr_date[:4]
        month = dlvr_date[5:7]
        return year, month
    raw_date = str(row.get("IntlCntrctDlvrReqDate", "") or "").strip()
    if len(raw_date) >= 6 and raw_date.isdigit():
        return raw_date[:4], raw_date[4:6]
    year = str(row.get("bssYear", "")).strip()
    month = str(row.get("bssMnth", "")).strip().zfill(2)
    return year, month


def _to_numeric(value) -> float:
    if value is None:
        return 0.0
    text = str(value).replace(",", "").strip()
    if text == "":
        return 0.0
    try:
        return float(text)
    except ValueError:
        return 0.0


def build_raw_dataframe(raw_rows: List[Dict], category_name: str) -> pd.DataFrame:
    # 원천 응답 -> 내부 표준 컬럼으로 정규화
    parsed = []
    for row in raw_rows:
        year, month = _extract_year_month(row)
        yyyymm = f"{year}{month}" if year and month else ""
        year_month = f"{year}-{month}" if year and month else ""
        product_name = str(row.get("prdctIdntNoNm", "") or row.get("prdctNm", "")).strip()
        amount = _to_numeric(row.get("prdctAmt") or row.get("dlvrReqAmt") or row.get("incdecAmt") or row.get("arsltAmt"))

        parsed.append(
            {
                "년월키": yyyymm,
                "년월": year_month,
                "품목명": category_name,
                "API품목명": product_name,
                "월실적": amount,
            }
        )

    df = pd.DataFrame(parsed)
    if not df.empty:
        df = df[df["년월"] != ""].copy()
    return df


def aggregate_dataframes(df_raw_all: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    반환 순서:
    - monthly_summary_df: 월별 합계 + 전월대비 증감률
    - item_monthly_df: 형식1 (년월/품목명/월실적/누계)
    - pivot_df: 형식2 (년월/품목별 컬럼/합계)
    - item_total_df: 품목별 총합
    """
    if df_raw_all.empty:
        empty = pd.DataFrame()
        return empty, empty, empty, empty

    # 형식1: 년월/품목명 단위 집계 + 누계
    item_monthly_df = (
        df_raw_all.groupby(["년월", "품목명"], as_index=False)["월실적"]
        .sum()
        .sort_values(["품목명", "년월"])
    )
    item_monthly_df["누계"] = item_monthly_df.groupby("품목명")["월실적"].cumsum()

    # 형식2: 년월 기준 피벗 (품목별 컬럼)
    pivot_df = (
        item_monthly_df.pivot_table(
            index="년월",
            columns="품목명",
            values="월실적",
            aggfunc="sum",
            fill_value=0,
        )
        .sort_index()
        .reset_index()
    )
    non_month_cols = [c for c in pivot_df.columns if c != "년월"]
    pivot_df["합계"] = pivot_df[non_month_cols].sum(axis=1)

    monthly_summary_df = pivot_df[["년월", "합계"]].copy().sort_values("년월")
    monthly_summary_df["전월대비증감률(%)"] = (
        monthly_summary_df["합계"].pct_change().fillna(0).mul(100).round(2)
    )

    item_total_df = (
        item_monthly_df.groupby("품목명", as_index=False)["월실적"]
        .sum()
        .sort_values("월실적", ascending=False)
        .rename(columns={"월실적": "품목합계"})
    )

    return monthly_summary_df, item_monthly_df, pivot_df, item_total_df
