from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Tuple

import pandas as pd


def process_market_share(
    raw_items: List[Dict], company_filter: str = "", category_filter: str = "", product_filter: str = ""
) -> Tuple[float, List[Dict], List[Dict]]:
    """
    조달청 원천 rows를 회사별 점유율 구조로 가공한다.
    반환: total_amount, company_rank(list), chart_data(list)
    """
    if not raw_items:
        return 0.0, [], []

    df = pd.DataFrame(raw_items)
    if df.empty:
        return 0.0, [], []

    # 실제 응답 스키마가 바뀌면 아래 후보 컬럼 목록을 먼저 수정한다.
    company_col_candidates = ["corpNm", "cntrctCorpBiznoNm", "cmpnyNm", "companyName", "entpNm", "dminsttNm"]
    amount_col_candidates = ["prdctAmt", "dlvrReqAmt", "incdecAmt", "arsltAmt", "exctvAmt", "amount"]
    category_col_candidates = ["prdctClsfcNo", "dtilPrdctClsfcNo", "prdctClsfcNoNm", "dtilPrdctClsfcNoNm", "prdctIdntNoNm"]
    product_col_candidates = ["prdctIdntNoNm", "prdctNm", "itemName", "item_name"]

    company_col = next((c for c in company_col_candidates if c in df.columns), None)
    amount_col = next((c for c in amount_col_candidates if c in df.columns), None)
    if not company_col or not amount_col:
        return 0.0, [], []

    available_category_cols = [c for c in category_col_candidates if c in df.columns]
    available_product_cols = [c for c in product_col_candidates if c in df.columns]
    work = df[list(dict.fromkeys([company_col, amount_col] + available_category_cols + available_product_cols))].copy()
    work = work.rename(columns={company_col: "company", amount_col: "amount"})
    work["company"] = work["company"].astype(str).str.strip()
    work["amount"] = (
        work["amount"].astype(str).str.replace(",", "", regex=False).replace("", "0").astype(float)
    )
    work = work[work["company"] != ""]

    # 프론트 category 파라미터로 품목코드(숫자) 또는 품목명(한글) 부분검색 지원
    if category_filter and available_category_cols:
        keyword = category_filter.strip()
        if keyword.isdigit():
            mask = False
            for col in [c for c in ["prdctClsfcNo", "dtilPrdctClsfcNo"] if c in available_category_cols]:
                mask = mask | work[col].astype(str).str.startswith(keyword, na=False)
            work = work[mask]
        else:
            mask = False
            lowered = keyword.lower()
            for col in available_category_cols:
                mask = mask | work[col].astype(str).str.lower().str.contains(lowered, na=False, regex=False)
            work = work[mask]

    # 프론트 company 파라미터로 업체명 부분검색 지원
    if company_filter:
        keyword = company_filter.strip().lower()
        work = work[work["company"].str.lower().str.contains(keyword, na=False, regex=False)]

    # 프론트 productName 파라미터로 제품명 부분검색 지원
    if product_filter and available_product_cols:
        lowered = product_filter.strip().lower()
        mask = False
        for col in available_product_cols:
            mask = mask | work[col].astype(str).str.lower().str.contains(lowered, na=False, regex=False)
        work = work[mask]

    if work.empty:
        return 0.0, [], []

    grouped = work.groupby("company", as_index=False)["amount"].sum().sort_values("amount", ascending=False)
    total_amount = float(grouped["amount"].sum())
    if total_amount <= 0:
        return 0.0, [], []

    grouped["share"] = (grouped["amount"] / total_amount * 100).round(2)
    grouped["cumulative_share"] = grouped["share"].cumsum().round(2)
    grouped["rank"] = range(1, len(grouped) + 1)

    rank_df = grouped[["rank", "company", "amount", "share", "cumulative_share"]].copy()
    chart_df = grouped[["company", "share"]].head(10).copy()
    return round(total_amount, 2), rank_df.to_dict(orient="records"), chart_df.to_dict(orient="records")


class DataProcessor:
    @staticmethod
    def _month_to_dt(month_str: str) -> datetime:
        return datetime.strptime(month_str, "%Y-%m")

    @staticmethod
    def _prev_month(month_str: str) -> str:
        dt = DataProcessor._month_to_dt(month_str)
        year = dt.year if dt.month > 1 else dt.year - 1
        month = dt.month - 1 if dt.month > 1 else 12
        return f"{year:04d}-{month:02d}"

    def build_dashboard(self, rows: List[Dict], start_month: str, end_month: str, top_n: int) -> Tuple[List[Dict], List[Dict], float]:
        if not rows:
            return [], [], 0.0

        df = pd.DataFrame(rows)
        if df.empty:
            return [], [], 0.0

        # 조회 기간 필터
        df = df[(df["period_month"] >= start_month) & (df["period_month"] <= end_month)].copy()
        if df.empty:
            return [], [], 0.0

        amount_by_manufacturer = df.groupby("manufacturer", as_index=False)["amount"].sum()
        amount_by_manufacturer = amount_by_manufacturer.sort_values("amount", ascending=False)

        total_amount = float(amount_by_manufacturer["amount"].sum())
        if total_amount <= 0:
            return [], [], 0.0

        top_manufacturers = amount_by_manufacturer.head(top_n)["manufacturer"].tolist()
        top_df = df[df["manufacturer"].isin(top_manufacturers)].copy()

        grouped = (
            top_df.groupby(
                ["category_main", "category_sub", "manufacturer", "item_name", "spec"], as_index=False
            )[["quantity", "amount"]]
            .sum()
            .sort_values("amount", ascending=False)
            .reset_index(drop=True)
        )

        grouped["market_share"] = (grouped["amount"] / total_amount * 100).round(2)
        grouped["cumulative_share"] = grouped["market_share"].cumsum().round(2)
        grouped["rank"] = grouped.index + 1

        # 전월 대비 증감률 계산 (제조사 기준)
        end_df = df[df["period_month"] == end_month].groupby("manufacturer", as_index=False)["amount"].sum()
        prev_month = self._prev_month(end_month)
        prev_df = df[df["period_month"] == prev_month].groupby("manufacturer", as_index=False)["amount"].sum()

        mom_map = {}
        prev_map = dict(zip(prev_df["manufacturer"], prev_df["amount"]))
        for _, row in end_df.iterrows():
            mfr = row["manufacturer"]
            current = float(row["amount"])
            prev = float(prev_map.get(mfr, 0))
            if prev <= 0:
                mom_map[mfr] = 0.0
            else:
                mom_map[mfr] = round((current - prev) / prev * 100, 2)

        grouped["mom_change_rate"] = grouped["manufacturer"].map(lambda m: mom_map.get(m, 0.0))

        table_rows = grouped[
            [
                "rank",
                "category_main",
                "category_sub",
                "manufacturer",
                "item_name",
                "spec",
                "quantity",
                "amount",
                "market_share",
                "cumulative_share",
                "mom_change_rate",
            ]
        ].to_dict(orient="records")

        chart_rows = (
            grouped.groupby("manufacturer", as_index=False)["market_share"]
            .sum()
            .sort_values("market_share", ascending=False)
            .head(10)
            .to_dict(orient="records")
        )

        return table_rows, chart_rows, round(total_amount, 2)
