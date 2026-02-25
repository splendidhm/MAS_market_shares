from datetime import datetime

import pandas as pd


def build_output_filename(end_yyyymm: str) -> str:
    suffix = end_yyyymm if end_yyyymm else datetime.now().strftime("%Y%m")
    return f"food_procurement_{suffix}.xlsx"


def export_to_excel(
    file_path: str,
    raw_df: pd.DataFrame,
    monthly_summary_df: pd.DataFrame,
    pivot_df: pd.DataFrame,
    item_monthly_df: pd.DataFrame,
    item_total_df: pd.DataFrame,
):
    with pd.ExcelWriter(file_path, engine="xlsxwriter") as writer:
        raw_df.to_excel(writer, index=False, sheet_name="원본데이터")

        monthly_summary_df.to_excel(writer, index=False, sheet_name="월별집계", startrow=0)
        # 같은 시트 아래에 피벗(형식2)도 같이 저장
        pivot_start_row = len(monthly_summary_df) + 3
        pivot_df.to_excel(writer, index=False, sheet_name="월별집계", startrow=pivot_start_row)

        item_monthly_df.to_excel(writer, index=False, sheet_name="품목별집계", startrow=0)
        item_total_start_row = len(item_monthly_df) + 3
        item_total_df.to_excel(
            writer, index=False, sheet_name="품목별집계", startrow=item_total_start_row
        )
