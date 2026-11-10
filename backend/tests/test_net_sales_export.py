import json
import unittest
from xml.etree import ElementTree as ET
from zipfile import ZipFile

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.database import Base
from app.models import FoodBatch, FoodPage
from app.services.excel_exporter import create_food_excel


class NetSalesExportTest(unittest.TestCase):
    def test_filtered_raw_rows_match_net_months_across_years(self):
        engine = create_engine("sqlite://")
        self.addCleanup(engine.dispose)
        Base.metadata.create_all(engine)
        with Session(engine) as db:
            batch = FoodBatch(scope="", start="20251201", end="20260228", complete=1)
            db.add(batch)
            db.flush()
            base = dict(corpNm="업체", prdctClsfcNo="5010", dtilPrdctClsfcNoNm="햄류",
                        prdctIdntNo="00123", prdctIdntNoNm="햄류, 브랜드, 햄(구운,냉동), 1kg",
                        dlvrReqRcptDate="2025-12-01", prdctAmt="1,101")
            rows = [base, dict(base, dlvrReqRcptDate="20260202", incdecAmt="-110"),
                    dict(base, incdecAmt=0), dict(base, corpNm="다른 회사")]
            db.add(FoodPage(batch_id=batch.id, number=1, records=json.dumps(rows)))
            db.commit()
            with create_food_excel(db, batch.start, batch.end, company="업체") as file, ZipFile(file) as archive:
                titles = [x.attrib["name"] for x in ET.fromstring(archive.read("xl/workbook.xml")).findall(".//{*}sheet")]
                self.assertEqual(titles[3:6], ["식품원천내역", "월별정제매출", "월별집계"])
                def records(page):
                    root = ET.fromstring(archive.read(f"xl/worksheets/sheet{page}.xml"))
                    return [["".join(c.itertext()) for c in row] for row in root.findall(".//{*}sheetData/{*}row")]
                self.assertEqual(len(records(4)), 4)
                data = records(5)
                self.assertEqual(len(data), 5)
                self.assertEqual(data[3][-3:], ["2025-12", "2026-01", "2026-02"])
                self.assertEqual(data[4][:5], ["업체", "햄류", "00123", "햄(구운,냉동)", "1kg"])
                for actual, gross in zip(data[4][5:], [991, 1101, 0, -110]):
                    self.assertAlmostEqual(float(actual), gross / 1.1)
                self.assertEqual(data[2][1:], data[4][5:])
