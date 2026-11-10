import unittest
from unittest.mock import patch

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.database import Base
from app.models import FoodPage
from app.services.food_report import report, sync_step, windows
from app.services.g2b_api import G2BApiError


class FoodCollectionTest(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite://")
        Base.metadata.create_all(engine)
        self.db = Session(engine)
        self.addCleanup(engine.dispose)
        self.addCleanup(self.db.close)

    def collect(self, limit=900, refresh=False):
        return sync_step(self.db, "20200201", "20200229", "", limit, refresh)

    def result(self):
        return report(self.db, "20200229", "20200229", "", "", "")

    @patch("app.services.food_report.sleep")
    @patch("app.services.food_report.G2BApiClient.fetch_page")
    def test_resume_and_atomic_refresh(self, fetch, sleep):
        base = dict(corpNm="업체", dlvrReqRcptDate="2020-02-29", prdctIdntNoNm="식품")
        food = dict(base, prdctClsfcNo="50112099", incdecAmt=100)
        nonfood = dict(base, prdctClsfcNo="30112099", incdecAmt=200)
        change = dict(food, incdecAmt=-30)
        fetch.side_effect = [(3, 2, [food, nonfood])] + [G2BApiError("실패")] * 3 + [(3, 2, [change])]
        self.assertFalse(self.collect()["complete"])
        with self.assertRaises(HTTPException) as stopped:
            self.collect(limit=1)
        self.assertEqual(stopped.exception.status_code, 429)
        with self.assertRaises(HTTPException):
            self.collect()
        self.assertFalse(self.result()["complete"])
        self.assertEqual(self.db.query(FoodPage).count(), 1)
        self.assertTrue(self.collect()["complete"])
        self.assertEqual([call.args[2] for call in fetch.call_args_list], [1, 2, 2, 2, 2])
        self.assertEqual(self.result()["item_rows"][0]["amount"], 70)
        self.assertTrue(self.collect()["complete"])
        self.assertEqual(fetch.call_count, 5)
        fetch.side_effect = [G2BApiError("실패")] * 3 + [(0, 999, [])]
        with self.assertRaises(HTTPException):
            self.collect(refresh=True)
        self.assertEqual(self.result()["total_amount"], 70)
        self.assertTrue(self.collect()["complete"])
        self.assertEqual(self.result()["total_amount"], 0)

    def test_date_boundaries(self):
        self.assertEqual(list(windows("20231231", "20240101")),
                         [("20231231", "20231231"), ("20240101", "20240101")])
        periods = list(windows("20240101", "20241231"))
        self.assertEqual(len(periods), 12)
        self.assertEqual(periods[1][1], "20240229")
