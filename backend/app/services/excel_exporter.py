from io import BytesIO
from typing import Dict, List

import pandas as pd


def create_excel(table_rows: List[Dict], chart_rows: List[Dict]) -> BytesIO:
    output = BytesIO()
    table_df = pd.DataFrame(table_rows)
    chart_df = pd.DataFrame(chart_rows)

    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        table_df.to_excel(writer, sheet_name="market_share", index=False)
        chart_df.to_excel(writer, sheet_name="top10_chart_data", index=False)

    output.seek(0)
    return output
