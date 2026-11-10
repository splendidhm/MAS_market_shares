# 식품 납품 내역 엑셀 저장

이 폴더에서 `pip install -r requirements.txt`를 실행하고 서비스키를 .env에 설정한다. `python main.py`에서 시작월과 종료월을 YYYYMM으로 입력하면 대시보드와 같은 식품 수집기로 전 페이지를 순회한다. DB 경로는 DATABASE_URL 설정을 따른다. 기본 저장 위치는 실행 폴더의 market_share.db이다.

완료한 페이지를 재사용하므로 중단한 기간을 다시 입력해 이어받을 수 있다. 완료 시 실행 폴더에 food_procurement_종료년월.xlsx를 저장한다. 업체별·품목별·월별 금액과 식품 원천 내역을 확인할 수 있다.
