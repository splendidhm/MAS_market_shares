import json
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from fastapi import HTTPException
from openpyxl import load_workbook
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.database import Base
from app.models import RegistrationBatch, RegistrationPage
from app.services.food_report import REGISTRATIONS, is_food, report, sync_step
from app.services.excel_exporter import create_registration_excel
from app.services.g2b_api import G2BApiClient, G2BApiError, G2BRateLimitError
from app.services.quota_service import get_today_call_count
from app.services.registrations import available_period, registration_report


class RegistrationTest(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite://")
        Base.metadata.create_all(engine)
        self.db = Session(engine)
        self.addCleanup(engine.dispose)
        self.addCleanup(self.db.close)
        self.food = dict(
            rgstDt="20260731", prdctClsfcNo="50112099", prdctIdntNo="00123456",
            prdctClsfcNoNm="식육가공품", dtilPrdctClsfcNoNm="소시지류",
            prdctSpecNm="후랑크 소시지", cntrctCorpNm="계약업체", prdctMakrNm="제조사",
            cntrctDate="20260630", cntrctPrceAmt="12000", shopngCntrctSno="1",
        )

    def sync(self, category="", refresh=False):
        return sync_step(self.db, "20260701", "20260731", category, 900, refresh,
                         source=REGISTRATIONS)

    def read(self, start="20260701", end="20260731", category="", company="", product="",
             page=1, size=50):
        return registration_report(self.db, start, end, category, company, product, page, size)

    @patch("app.services.g2b_api.requests.get")
    def test_registration_operation_and_page_validation(self, get):
        client = G2BApiClient(registration=True)
        client.service_key = "test"
        response = get.return_value
        response.status_code = 200
        body = dict(items={"item": self.food}, pageNo=1, numOfRows=999, totalCount=1)
        response.json.return_value = {"response": {"header": {"resultCode": "00"}, "body": body}}
        total, size, rows = client.fetch_page("20260701", "20260731", 1, "prdctClsfcNoNm", "식육가공품")
        self.assertEqual((total, size, rows), (1, 999, [self.food]))
        self.assertEqual(get.call_args.args[0],
                         "https://apis.data.go.kr/1230000/at/ShoppingMallPrdctInfoService/getShoppingMallPrdctInfoList")
        self.assertEqual(get.call_args.kwargs["params"], dict(
            serviceKey="test", type="json", inqryDiv="1", inqryBgnDate="20260701",
            inqryEndDate="20260731", pageNo=1, numOfRows=999, prdctClsfcNoNm="식육가공품",
        ))
        for change in ({"pageNo": 2}, {"numOfRows": 1}, {"totalCount": 2}, {"items": ["bad"]}):
            with self.subTest(change=change):
                response.json.return_value["response"]["body"] = {**body, **change}
                with self.assertRaises(G2BApiError):
                    client.fetch_page("20260701", "20260731", 1)

    @patch("app.services.food_report.G2BApiClient.fetch_page")
    def test_resume_food_scope_and_cache_isolation(self, fetch):
        # The identifier's prefix does not determine whether the product is food.
        nonfood = dict(self.food, prdctClsfcNo="56100000", prdctIdntNo="50123456")
        tobacco = dict(self.food, prdctClsfcNo="50210000")
        other_contract = dict(self.food, rgstDt="20260701", shopngCntrctSno="2")
        fetch.side_effect = [
            (4, 2, [self.food, nonfood]), G2BRateLimitError("한도"),
            (4, 2, [tobacco, other_contract]),
        ]
        first = self.sync()
        self.assertFalse(first["complete"])
        self.assertEqual(
            {key: first[key] for key in (
                "current_page", "total_pages", "scanned", "expected", "page_rows", "food_rows"
            )},
            dict(current_page=1, total_pages=2, scanned=2, expected=4, page_rows=2, food_rows=1),
        )
        self.assertIsNone(self.read()["total"])
        with self.assertRaises(HTTPException) as limited:
            self.sync()
        self.assertEqual(limited.exception.status_code, 429)
        self.assertTrue(self.sync()["complete"])
        self.assertEqual([call.args[2] for call in fetch.call_args_list], [1, 2, 2])
        self.sync("소시지류")
        self.assertEqual(get_today_call_count(self.db), 3)
        batch = self.db.query(RegistrationBatch).one()
        self.assertEqual((batch.next_page, batch.scanned, batch.expected, batch.complete), (3, 4, 4, 1))
        saved = [row for page in self.db.query(RegistrationPage) for row in json.loads(page.records)]
        self.assertEqual(len(saved), 2)
        self.assertTrue(all(map(is_food, saved)))
        self.assertFalse(report(self.db, batch.start, batch.end, "", "", "")["complete"])
        self.assertEqual(self.read()["total"], 2)
        self.assertEqual(self.read(page=2, size=1)["rows"], [other_contract])
        self.assertEqual(self.read()["categories"], ["세부품명/소시지류", "품명/식육가공품"])
        self.assertEqual(self.read(start="20260731", company="제조", product="00123456")["rows"], [self.food])
        self.assertEqual(self.read(company="계약", product="후랑크", category="축산가공품")["total"], 2)
        self.assertEqual(self.read(category="세부품명/소시지")["total"], 0)
        self.assertEqual(self.read(category="김치")["rows"], [])
        self.assertFalse(self.read(end="20260801")["complete"])
        self.assertEqual(self.read(end="20260801")["rows"], [])

    @patch("app.services.food_report.G2BApiClient.fetch_page")
    def test_preset_scope_and_empty_refresh(self, fetch):
        fetch.side_effect = [(1, 999, [self.food]), G2BRateLimitError("한도"), (0, 999, [])]
        self.sync("소시지류")
        self.assertEqual(fetch.call_args.args[3:], ("dtilPrdctClsfcNoNm", "소시지"))
        self.assertFalse(self.read()["complete"])
        self.assertEqual(self.read(category="소시지류")["total"], 1)
        with self.assertRaises(HTTPException):
            self.sync("소시지류", refresh=True)
        self.assertEqual(self.read(category="소시지류")["total"], 1)
        self.sync("소시지류")
        result = self.read(category="소시지류")
        self.assertTrue(result["complete"])
        self.assertEqual(result["total"], 0)

    def test_registration_cutoff_and_invalid_ranges(self):
        today = datetime.now(timezone(timedelta(hours=9))).date()
        last = (today - timedelta(days=1)).strftime("%Y%m%d")
        self.assertEqual(available_period(last, today.strftime("%Y%m%d")), (last, last))
        for start, end in [("20260230", "20260301"), ("20260301", "20260228"),
                           (today.strftime("%Y%m%d"), "99991231"), ("20260701", "99999999")]:
            with self.subTest(start=start, end=end), self.assertRaises(HTTPException):
                available_period(start, end)

    def test_registration_excel_preprocessing_filters_and_sheets(self):
        rows = [
            dict(self.food, prdctSpecNm="소시지류, 브랜드, 후랑크소시지, 1kg",
                 cntrctCorpNm="가업체", cntrctPrceAmt="12,000"),
            dict(self.food, prdctIdntNo="00876543", prdctSpecNm="분리가 어려운 제품",
                 cntrctCorpNm="나업체", rgstDt="20260701", cntrctPrceAmt="3500"),
        ]
        batch = RegistrationBatch(start="20260701", end="20260731", scope="",
                                  next_page=2, scanned=2, expected=2, complete=1)
        self.db.add(batch)
        self.db.flush()
        self.db.add(RegistrationPage(batch_id=batch.id, number=1,
                                     records=json.dumps(rows, ensure_ascii=False)))
        self.db.commit()

        with create_registration_excel(
            self.db, "20260701", "20260731", company="가업체", product="후랑크"
        ) as output:
            workbook = load_workbook(output, read_only=True, data_only=True)
            self.assertEqual(workbook.sheetnames, ["품목등록정제", "품목등록원천", "월별등록집계"])
            cleaned = list(workbook["품목등록정제"].values)
            self.assertEqual(cleaned[0][:9], (
                "등록일", "계약업체", "제조사", "품명", "세부품명", "물품식별번호",
                "제품명", "규격", "계약단가(원)",
            ))
            self.assertEqual(cleaned[1][1], "가업체")
            self.assertEqual(cleaned[1][5:9], ("00123456", "후랑크소시지", "1kg", 12000))
            self.assertEqual(len(cleaned), 2)
            raw = list(workbook["품목등록원천"].values)
            self.assertEqual(raw[0][raw[0].index("prdctIdntNo")], "prdctIdntNo")
            self.assertEqual(raw[1][raw[0].index("prdctIdntNo")], "00123456")
            self.assertEqual(list(workbook["월별등록집계"].values)[1], ("2026-07", "소시지류", 1))
            workbook.close()

        with create_registration_excel(self.db, "20260701", "20260731", company="없는업체") as output:
            workbook = load_workbook(output, read_only=True, data_only=True)
            self.assertEqual(len(list(workbook["품목등록정제"].values)), 1)
            self.assertEqual(len(list(workbook["품목등록원천"].values)), 1)
            workbook.close()

        with self.assertRaises(HTTPException) as incomplete:
            create_registration_excel(self.db, "20260701", "20260801")
        self.assertEqual(incomplete.exception.status_code, 409)
