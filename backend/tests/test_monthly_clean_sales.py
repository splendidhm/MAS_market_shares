import json
import unittest

from fastapi import HTTPException
from openpyxl import load_workbook
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.database import Base
from app.models import FoodBatch, FoodPage
from app.services.excel_exporter import create_food_excel, split_product_spec
from app.services.food_report import windows


class MonthlyCleanSalesTest(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite://")
        Base.metadata.create_all(engine)
        self.db = Session(engine)
        self.addCleanup(engine.dispose)
        self.addCleanup(self.db.close)

    def row(self, day, amount, *, vendor="가업체", description="햄류, 씨제이제일제당, 스팸클래식, 1.81kg", code="0012345", **extra):
        result = dict(corpNm=vendor, dtilPrdctClsfcNoNm="햄류", prdctClsfcNoNm="식육가공품",
                      prdctClsfcNo="50112099", prdctIdntNo=code, prdctIdntNoNm=description,
                      dlvrReqRcptDate=day, incdecAmt=amount)
        result.update(extra)
        return result

    def populate(self, start, end, rows):
        for a, b in windows(start, end):
            matching = [row for row in rows if a <= row["dlvrReqRcptDate"].replace("-", "") <= b]
            batch = FoodBatch(start=a, end=b, scope="", next_page=2, scanned=len(matching),
                              expected=len(matching), complete=1)
            self.db.add(batch)
            self.db.flush()
            self.db.add(FoodPage(batch_id=batch.id, number=1, records=json.dumps(matching, ensure_ascii=False)))
        self.db.commit()

    def workbook(self, start, end, **filters):
        output = create_food_excel(self.db, start, end, **filters)
        self.addCleanup(output.close)
        workbook = load_workbook(output, read_only=True, data_only=True)
        self.addCleanup(workbook.close)
        return workbook

    def test_one_month_signed_amount_fallback_and_identification_code(self):
        rows = [self.row("2026-07-01", 110), self.row("2026-07-02", -22),
                self.row("2026-07-03", None, prdctAmt="33"),
                self.row("2026-07-04", "", prdctAmt="0")]
        self.populate("20260701", "20260731", rows)
        book = self.workbook("20260701", "20260731")
        self.assertEqual(book.sheetnames, ["업체별", "업체별품목", "품목별", "식품원천내역", "월별정제매출", "월별집계"])
        sheet = book["월별정제매출"]
        self.assertEqual(sheet.max_row, 5)
        self.assertEqual(sheet["A1"].value, "다수공급자계약 월별 매출 분석 (부가세 별도)")
        self.assertIn("20260701 ~ 20260731", sheet["A2"].value)
        self.assertIn("÷ 1.1", sheet["A2"].value)
        self.assertEqual([sheet.cell(4, c).value for c in range(1, 8)],
                         ["업체명", "세부품명", "물품식별번호", "제품명", "규격", "누계", "7월"])
        self.assertEqual([sheet.cell(5, c).value for c in range(1, 6)],
                         ["가업체", "햄류", "0012345", "스팸클래식", "1.81kg"])
        self.assertAlmostEqual(sheet["F5"].value, 110)
        self.assertAlmostEqual(sheet["G5"].value, 110)
        self.assertAlmostEqual(sheet["F3"].value, 110)
        source = book["식품원천내역"]
        headers = [cell.value for cell in source[1]]
        gross = sum(int(str(row[headers.index("incdecAmt")] if row[headers.index("incdecAmt")] not in (None, "")
                            else row[headers.index("prdctAmt")])) for row in list(source.values)[1:])
        self.assertAlmostEqual(sheet["F3"].value * 1.1, gross)

    def test_multiple_months_zero_month_sorting_and_totals(self):
        rows = [self.row("2026-01-10", 110), self.row("2026-03-10", 220),
                self.row("2026-01-11", -22), self.row("2026-03-12", 55, vendor="나업체")]
        self.populate("20260101", "20260331", rows)
        book = self.workbook("20260101", "20260331")
        sheet = book["월별정제매출"]
        self.assertEqual([sheet.cell(4, c).value for c in range(7, 10)], ["1월", "2월", "3월"])
        self.assertEqual(sheet["A5"].value, "가업체")
        self.assertEqual(sheet["A6"].value, "나업체")
        self.assertEqual(sheet["H5"].value, 0)
        self.assertEqual(sheet["H6"].value, 0)
        self.assertAlmostEqual(sheet["F5"].value, 280)
        self.assertAlmostEqual(sheet["F6"].value, 50)
        self.assertAlmostEqual(sheet["F3"].value, 330)
        for row in (3, 5, 6):
            self.assertAlmostEqual(sheet.cell(row, 6).value,
                                   sum(sheet.cell(row, col).value for col in range(7, 10)))
        self.assertAlmostEqual(sheet["F3"].value * 1.1, sum(x["incdecAmt"] for x in rows))

    def test_cross_year_and_filters(self):
        rows = [self.row("2025-12-10", 110), self.row("2026-01-10", 220),
                self.row("2026-01-11", 330, vendor="나업체"),
                self.row("2026-01-12", 440, description="햄류, 브랜드, 다른제품, 1kg")]
        self.populate("20251201", "20260228", rows)
        book = self.workbook("20251201", "20260228", company="가업체", product="스팸")
        sheet = book["월별정제매출"]
        self.assertEqual([sheet.cell(4, col).value for col in range(7, 10)],
                         ["2025-12", "2026-01", "2026-02"])
        self.assertEqual(sheet.max_row, 5)
        self.assertAlmostEqual(sheet["F5"].value, 300)
        self.assertEqual(sheet["I5"].value, 0)
        self.assertEqual(book["식품원천내역"].max_row, 3)
        self.assertAlmostEqual(sheet["F3"].value * 1.1, 330)

    def test_product_and_specification_with_internal_commas(self):
        self.assertEqual(split_product_spec("햄류, 씨제이제일제당, 스팸클래식, 1.81kg"),
                         ("스팸클래식", "1.81kg"))
        self.assertEqual(split_product_spec("햄류, 브랜드, 스팸, 클래식, 1kg, 냉장"),
                         ("스팸, 클래식", "1kg, 냉장"))
        self.assertEqual(split_product_spec("햄류, 브랜드, 스팸, 1,000g, 냉장"),
                         ("스팸", "1,000g, 냉장"))
        self.assertEqual(split_product_spec("불명확한, 설명, 제품, 추가, 항목"),
                         ("불명확한, 설명, 제품, 추가, 항목", ""))
        self.assertEqual(split_product_spec("햄류, 브랜드, 제품, 불명확"),
                         ("햄류, 브랜드, 제품, 불명확", ""))
        rows = [self.row("2026-07-01", 110, description="햄류, 브랜드, 스팸, 클래식, 1kg, 냉장")]
        self.populate("20260701", "20260731", rows)
        sheet = self.workbook("20260701", "20260731")["월별정제매출"]
        self.assertEqual(sheet["D5"].value, "스팸, 클래식")
        self.assertEqual(sheet["E5"].value, "1kg, 냉장")

    def test_incomplete_period_blocks_download(self):
        with self.assertRaises(HTTPException) as caught:
            create_food_excel(self.db, "20260701", "20260731")
        self.assertEqual(caught.exception.status_code, 409)


if __name__ == "__main__":
    unittest.main()
