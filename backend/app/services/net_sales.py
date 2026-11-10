"""VAT-exclusive item sales, derived only from the filtered raw export rows."""
import re
from collections import defaultdict

from app.services.food_report import windows


class NetSales:
    def __init__(self, start, end):
        self.months = [first[:6] for first, _ in windows(start, end)]
        self.items = defaultdict(lambda: defaultdict(int))
        self.start, self.end = start, end

    def add(self, row, month, amount):
        description = str(row.get("prdctIdntNoNm") or "").strip()
        parts = re.split(r",\s+", description, maxsplit=3)
        if len(parts) < 4:
            parts = [p.strip() for p in description.split(",", 3)]
        # Standard G2B description: classification, brand, product, specification.
        # Preserve unfamiliar descriptions whole instead of guessing a size.
        name, spec = (parts[2], parts[3]) if len(parts) == 4 else (description, "")
        key = (str(row.get("corpNm") or "업체명 미제공").strip(),
               str(row.get("dtilPrdctClsfcNoNm") or "").strip(),
               str(row.get("prdctIdntNo") or "").strip(), name, spec)
        self.items[key][month] += amount

    def write(self, book, sheet):
        single_year = self.start[:4] == self.end[:4]
        labels = [f"{int(m[4:])}월" if single_year else f"{m[:4]}-{m[4:]}" for m in self.months]
        headers = ["업체명", "세부품명", "물품식별번호", "제품명", "규격", "누계", *labels]
        head = book.add_format({"bold": True, "font_color": "white", "bg_color": "#245469"})
        money = book.add_format({"num_format": "#,##0;[Red](#,##0);0"})
        totals = [sum(values.get(m, 0) for values in self.items.values()) for m in self.months]

        def setup(page):
            page.write(0, 0, "다수공급자계약 월별 매출 분석 (부가세 별도)", head)
            page.write(1, 0, f"조회 기간: {self.start} ~ {self.end}  |  매출액 ÷ 1.1 (원)")
            page.write(2, 0, "전체 합계")
            page.write_row(2, 5, [n * 10 / 11 for n in [sum(totals), *totals]], money)
            page.write_row(3, 0, headers, head)
            page.set_column(0, 0, 30)
            page.set_column(1, 2, 18)
            page.set_column(3, 3, 46)
            page.set_column(4, 4, 30)
            page.set_column(5, len(headers) - 1, 19)
            page.freeze_panes(4, 3)

        setup(sheet)
        count = 0
        for i, (key, values) in enumerate(sorted(self.items.items(), key=lambda kv: (-sum(kv[1].values()), kv[0]))):
            count = i % (1048576 - 4)
            if i and not count:
                sheet.autofilter(3, 0, 1048575, len(headers) - 1)
                sheet = book.add_worksheet(f"월별정제매출_{i // (1048576 - 4) + 1}")
                setup(sheet)
            sheet.write_row(count + 4, 0, key)
            amounts = [values.get(m, 0) for m in self.months]
            sheet.write_row(count + 4, 5, [n * 10 / 11 for n in [sum(amounts), *amounts]], money)
        sheet.autofilter(3, 0, count + 4 if self.items else 3, len(headers) - 1)
