from io import BytesIO
from typing import Dict, List
from collections import defaultdict
from datetime import datetime
from decimal import Decimal, InvalidOperation
import re

import pandas as pd


_SPEC_START = re.compile(r"^\s*\d[\d,.]*\s*(?:kg|mg|g|ml|l|ℓ|개|입|봉|팩|박스|캔|병|포|장|매|인분|세트)(?=\W|\d|$)", re.IGNORECASE)
_MONEY_FORMAT = '#,##0;[Red](#,##0);0'


def split_product_spec(description):
    """Split the usual classification, maker, product, specification form."""
    original = str(description or "").strip()
    prefix = original.split(",", 2)
    if len(prefix) != 3 or not all(part.strip() for part in prefix[:2]):
        return original, ""
    remainder = prefix[2].strip()
    for match in re.finditer(r",\s*", remainder):
        candidate = remainder[match.end():]
        if _SPEC_START.match(candidate):
            return remainder[:match.start()].strip(), candidate.strip()
    return original, ""


def _month_labels(start, end):
    first = datetime.strptime(start, "%Y%m%d")
    last = datetime.strptime(end, "%Y%m%d")
    months = []
    year, month = first.year, first.month
    while (year, month) <= (last.year, last.month):
        key = f"{year:04d}-{month:02d}"
        label = f"{month}월" if first.year == last.year else key
        months.append((key, label))
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return months


def _excluding_vat(amount):
    return float(Decimal(amount) * Decimal(10) / Decimal(11))


def _excel_number(value):
    try:
        number = Decimal(str(value or 0).replace(",", ""))
    except InvalidOperation:
        return 0
    return int(number) if number == number.to_integral_value() else float(number)


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
    cleaned = defaultdict(lambda: defaultdict(int))
    cleaned_totals = defaultdict(int)
    months = _month_labels(start, end)
    with TemporaryFile(mode="w+t", encoding="utf-8") as records:
        def collect(row):
            columns.update(dict.fromkeys(row))
            day = str(row["dlvrReqRcptDate"]).replace("-", "")
            month = f"{day[:4]}-{day[4:6]}"
            key = (row["dlvrReqRcptDate"][:7], row.get("dtilPrdctClsfcNoNm") or row.get("prdctClsfcNoNm") or "")
            value = row.get("incdecAmt")
            if value in (None, ""):
                value = row.get("prdctAmt") or 0
            amount = int(str(value).replace(",", ""))
            monthly[key] = monthly.get(key, 0) + amount
            product_name, specification = split_product_spec(row.get("prdctIdntNoNm"))
            identity = (str(row.get("corpNm") or "업체명 미제공"),
                        str(row.get("dtilPrdctClsfcNoNm") or ""),
                        str(row.get("prdctIdntNo") or ""), product_name, specification)
            cleaned[identity][month] += amount
            cleaned_totals[month] += amount
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
                records.seek(0)
                keys = list(columns)
                def raw_values():
                    for line in records:
                        row = json.loads(line)
                        yield [row.get(key) for key in keys]
                sheet_rows("식품원천내역", keys, raw_values())
                money_format = book.add_format({"num_format": _MONEY_FORMAT})
                title_format = book.add_format({"bold": True, "font_size": 15})
                header_format = book.add_format({"bold": True, "bg_color": "#DDEBF7"})
                text_format = book.add_format({"num_format": "@"})
                labels = [label for _, label in months]
                gross_total = sum(cleaned_totals.values())
                sorted_rows = sorted(cleaned.items(), key=lambda item: (-sum(item[1].values()), item[0]))
                max_data_rows = 1048576 - 4
                for part, first_row in enumerate(range(0, max(len(sorted_rows), 1), max_data_rows), 1):
                    name = "월별정제매출" if part == 1 else f"월별정제매출_{part}"
                    sheet = book.add_worksheet(name)
                    sheet.set_column(0, 0, 26)
                    sheet.set_column(1, 1, 26)
                    sheet.set_column(2, 2, 20, text_format)
                    sheet.set_column(3, 3, 48)
                    sheet.set_column(4, 4, 38)
                    sheet.set_column(5, 5 + len(months), 19, money_format)
                    sheet.write(0, 0, "다수공급자계약 월별 매출 분석 (부가세 별도)", title_format)
                    sheet.write(1, 0, f"조회 기간: {start} ~ {end} | 계산 기준: 매출액 ÷ 1.1")
                    sheet.write(2, 0, "전체 합계")
                    sheet.write_number(2, 5, _excluding_vat(gross_total), money_format)
                    for offset, (month, _) in enumerate(months, 6):
                        sheet.write_number(2, offset, _excluding_vat(cleaned_totals[month]), money_format)
                    sheet.write_row(3, 0, ["업체명", "세부품명", "물품식별번호", "제품명", "규격", "누계", *labels], header_format)
                    portion = sorted_rows[first_row:first_row + max_data_rows]
                    for offset, (identity, amounts) in enumerate(portion, 4):
                        for col, value in enumerate(identity):
                            sheet.write_string(offset, col, value)
                        sheet.write_number(offset, 5, _excluding_vat(sum(amounts.values())), money_format)
                        for col, (month, _) in enumerate(months, 6):
                            sheet.write_number(offset, col, _excluding_vat(amounts.get(month, 0)), money_format)
                    sheet.autofilter(3, 0, max(4, 3 + len(portion)), 5 + len(months))
                    sheet.freeze_panes(4, 0)
                sheet_rows("월별집계", ["접수월","세부품명","납품요구 순액(원)"],
                           ([*k, v] for k, v in sorted(monthly.items())))
            output.seek(0)
            return output
        except BaseException:
            output.close()
            raise


def create_registration_excel(db, start, end, category="", company="", product=""):
    """Write filtered registration rows and their normalized product fields."""
    import json
    from tempfile import TemporaryFile

    import xlsxwriter
    from fastapi import HTTPException
    from app.services.registrations import registration_records

    records, missing, _ = registration_records(db, start, end, category, company, product)
    if missing:
        raise HTTPException(409, "선택 기간의 식품 품목등록 DB 동기화를 완료해주세요.")

    columns = dict.fromkeys([
        "rgstDt", "prdctClsfcNo", "prdctClsfcNoNm", "dtilPrdctClsfcNo",
        "dtilPrdctClsfcNoNm", "prdctIdntNo", "prdctSpecNm", "cntrctCorpNm",
        "prdctMakrNm", "cntrctPrceAmt", "prdctUnit", "shopngCntrctNo",
        "shopngCntrctSno", "cntrctDate", "cntrctBgnDate", "cntrctEndDate",
        "masYn", "regtCncelYn", "prodctCertList", "prdctImgUrl",
    ])
    monthly = defaultdict(int)
    row_count = 0
    with TemporaryFile(mode="w+t", encoding="utf-8") as raw_records:
        for row in records:
            columns.update(dict.fromkeys(row))
            registered = str(row.get("rgstDt") or "").replace("-", "")
            monthly[(registered[:6], str(row.get("dtilPrdctClsfcNoNm") or
                                            row.get("prdctClsfcNoNm") or ""))] += 1
            raw_records.write(json.dumps(row, ensure_ascii=False) + "\n")
            row_count += 1

        output = TemporaryFile()
        try:
            with xlsxwriter.Workbook(output, {"constant_memory": True, "strings_to_urls": False,
                                             "strings_to_formulas": False, "use_zip64": True}) as book:
                header_format = book.add_format({"bold": True, "bg_color": "#DDEBF7"})
                money_format = book.add_format({"num_format": _MONEY_FORMAT})
                text_format = book.add_format({"num_format": "@"})

                cleaned_headers = [
                    "등록일", "계약업체", "제조사", "품명", "세부품명", "물품식별번호",
                    "제품명", "규격", "계약단가(원)", "단위", "쇼핑계약번호",
                    "계약일", "계약시작일", "계약종료일", "다수공급자계약여부", "등록해지여부",
                ]
                max_data_rows = 1048575

                def cleaned_sheet(part, first_row):
                    name = "품목등록정제" if part == 1 else f"품목등록정제_{part}"
                    sheet = book.add_worksheet(name)
                    sheet.freeze_panes(1, 0)
                    portion = min(max_data_rows, max(row_count - first_row, 0))
                    sheet.autofilter(0, 0, max(portion, 1), 15)
                    sheet.set_column(0, 0, 12)
                    sheet.set_column(1, 4, 24)
                    sheet.set_column(5, 5, 18, text_format)
                    sheet.set_column(6, 6, 42)
                    sheet.set_column(7, 7, 28)
                    sheet.set_column(8, 8, 16, money_format)
                    sheet.set_column(9, 9, 10)
                    sheet.set_column(10, 10, 22, text_format)
                    sheet.set_column(11, 13, 12)
                    sheet.set_column(14, 15, 14)
                    sheet.write_row(0, 0, cleaned_headers, header_format)
                    return sheet

                raw_records.seek(0)
                cleaned = cleaned_sheet(1, 0)
                for index, line in enumerate(raw_records):
                    if index and index % max_data_rows == 0:
                        cleaned = cleaned_sheet(index // max_data_rows + 1, index)
                    row = json.loads(line)
                    product_name, specification = split_product_spec(row.get("prdctSpecNm"))
                    values = [
                        row.get("rgstDt"), row.get("cntrctCorpNm"), row.get("prdctMakrNm"),
                        row.get("prdctClsfcNoNm"), row.get("dtilPrdctClsfcNoNm"),
                        str(row.get("prdctIdntNo") or ""), product_name, specification,
                        _excel_number(row.get("cntrctPrceAmt")),
                        row.get("prdctUnit"), str(row.get("shopngCntrctNo") or ""),
                        row.get("cntrctDate"), row.get("cntrctBgnDate"), row.get("cntrctEndDate"),
                        row.get("masYn"), row.get("regtCncelYn"),
                    ]
                    cleaned.write_row(index % max_data_rows + 1, 0, values)

                keys = list(columns)

                def raw_sheet(part, first_row):
                    name = "품목등록원천" if part == 1 else f"품목등록원천_{part}"
                    sheet = book.add_worksheet(name)
                    sheet.freeze_panes(1, 0)
                    portion = min(max_data_rows, max(row_count - first_row, 0))
                    sheet.autofilter(0, 0, max(portion, 1), max(len(keys) - 1, 0))
                    sheet.write_row(0, 0, keys, header_format)
                    return sheet

                raw_records.seek(0)
                raw = raw_sheet(1, 0)
                for index, line in enumerate(raw_records):
                    if index and index % max_data_rows == 0:
                        raw = raw_sheet(index // max_data_rows + 1, index)
                    row = json.loads(line)
                    raw.write_row(index % max_data_rows + 1, 0, [row.get(key) for key in keys])

                summary = book.add_worksheet("월별등록집계")
                summary.freeze_panes(1, 0)
                summary.write_row(0, 0, ["등록월", "세부품명", "등록건수"], header_format)
                for index, ((month, detail), count) in enumerate(sorted(monthly.items()), 1):
                    label = f"{month[:4]}-{month[4:6]}" if len(month) == 6 else month
                    summary.write_row(index, 0, [label, detail, count])
                summary.autofilter(0, 0, max(len(monthly), 1), 2)
            output.seek(0)
            return output
        except BaseException:
            output.close()
            raise
