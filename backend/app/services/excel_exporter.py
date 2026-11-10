from io import BytesIO
from typing import Dict, List

import pandas as pd


def create_excel(table_rows: List[Dict], chart_rows: List[Dict]) -> BytesIO:
    output = BytesIO()
    table_df = pd.DataFrame(table_rows)
    chart_df = pd.DataFrame(chart_rows)

    with pd.ExcelWriter(output, engine="xlsxwriter", engine_kwargs={"options": {"strings_to_urls": False, "strings_to_formulas": False}}) as writer:
        table_df.to_excel(writer, sheet_name="market_share", index=False)
        chart_df.to_excel(writer, sheet_name="top10_chart_data", index=False)

    output.seek(0)
    return output


def create_food_excel(db, start, end, category="", company="", product=""):
    """Spool original rows to disk to bound memory across multiple years."""
    import json
    from tempfile import TemporaryFile

    import xlsxwriter
    from fastapi import HTTPException
    from app.services.food_report import report

    columns = {}
    monthly = {}
    with TemporaryFile(mode="w+t", encoding="utf-8") as records:
        def collect(row):
            columns.update(dict.fromkeys(row))
            key = (row["dlvrReqRcptDate"][:7], row.get("dtilPrdctClsfcNoNm") or row.get("prdctClsfcNoNm") or "")
            value = row.get("incdecAmt")
            if value in (None, ""):
                value = row.get("prdctAmt") or 0
            monthly[key] = monthly.get(key, 0) + int(str(value).replace(",", ""))
            records.write(json.dumps(row, ensure_ascii=False) + "\n")

        result = report(db, start, end, category, company, product, on_record=collect)
        if not result["complete"]:
            raise HTTPException(409, "선택 기간의 식품 DB 동기화를 완료해주세요.")
        output = TemporaryFile()
        try:
            with xlsxwriter.Workbook(output, {"constant_memory": True, "strings_to_urls": False,
                                             "strings_to_formulas": False, "use_zip64": True}) as book:
                def sheet_rows(title, headers, rows):
                    sheet = book.add_worksheet(title)
                    sheet.write_row(0, 0, headers)
                    for index, values in enumerate(rows):
                        offset = index % 1048575
                        if index and offset == 0:
                            sheet = book.add_worksheet(f"{title}_{index // 1048575 + 1}")
                            sheet.write_row(0, 0, headers)
                        sheet.write_row(offset + 1, 0, values)

                headers = ["순위", "업체명", "납품요구 순액(원)", "점유율(%)", "누적점유율(%)"]
                sheet_rows("업체별", headers, ([r[k] for k in ("rank","company","amount","share","cumulative_share")]
                                            for r in result["company_rank"]))
                sheet_rows("업체별품목", ["업체명","물품식별번호","물품규격명","납품요구 순액(원)"],
                           ([r[k] for k in ("company","code","product","amount")] for r in result["product_rows"]))
                sheet_rows("품목별", ["물품식별번호","물품규격명","납품요구 순액(원)"],
                           ([r[k] for k in ("code","product","amount")] for r in result["item_rows"]))
                sheet_rows("월별집계", ["접수월","세부품명","납품요구 순액(원)"],
                           ([*k, v] for k, v in sorted(monthly.items())))
                records.seek(0)
                keys = list(columns)
                def raw_values():
                    for line in records:
                        row = json.loads(line)
                        yield [row.get(key) for key in keys]
                sheet_rows("식품원천내역", keys, raw_values())
            output.seek(0)
            return output
        except BaseException:
            output.close()
            raise
