"""Standalone food report using the same resumable collector as the dashboard."""
import calendar
import os
import re
import shutil
import sys
from pathlib import Path
from tempfile import NamedTemporaryFile

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
load_dotenv(Path(__file__).with_name(".env"), override=False)
from app.core.database import Base, engine, SessionLocal
from app.services.food_report import sync_step
from app.services.excel_exporter import create_food_excel


def validate_yyyymm(value: str) -> bool:
    return bool(re.fullmatch(r"[0-9]{6}", value)) and int(value[:4]) > 0 and 1 <= int(value[4:]) <= 12


def prompt_period() -> (str, str):
    while True:
        start_yyyymm = input("조회 시작년월(YYYYMM): ").strip()
        end_yyyymm = input("조회 종료년월(YYYYMM): ").strip()

        if not validate_yyyymm(start_yyyymm) or not validate_yyyymm(end_yyyymm):
            print("형식 오류: YYYYMM 6자리로 입력해주세요.")
            continue
        if start_yyyymm > end_yyyymm:
            print("입력 오류: 시작년월은 종료년월보다 작거나 같아야 합니다.")
            continue
        return start_yyyymm, end_yyyymm


def main():
    first, last = prompt_period()
    start = first + "01"
    end = last + str(calendar.monthrange(int(last[:4]), int(last[4:]))[1])
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        while True:
            state = sync_step(db, start, end, "", int(os.getenv("G2B_DAILY_CALL_LIMIT", "900")))
            print(state["progress"], flush=True)
            if state["complete"]:
                break
        target = Path.cwd() / f"food_procurement_{last}.xlsx"
        with create_food_excel(db, start, end) as book:
            with NamedTemporaryFile(dir=target.parent, suffix=".xlsx", delete=False) as tmp:
                tmp_path = Path(tmp.name)
                try:
                    shutil.copyfileobj(book, tmp)
                except BaseException:
                    tmp.close()
                    tmp_path.unlink(missing_ok=True)
                    raise
            try:
                tmp_path.replace(target)
            finally:
                tmp_path.unlink(missing_ok=True)
        print(f"엑셀 저장 완료: {target}")


if __name__ == "__main__":
    main()
