# MAS_market_shares 인수인계

## 2026-11-12 나라장터 품목등록 조회

- 왼쪽 첫 메뉴와 매출 페이지 중앙 제목은 `나라장터 매출 현황 조회`로 통일했다. 두 번째 메뉴는 `나라장터 품목등록 내역 조회`다.
- 품목등록 메뉴에서 등록 기간과 식품을 선택해 `DB 동기화`를 누르면 등록 행을 가져와 바로 표시한다. 이후 `조회`는 저장 자료를 검색한다. 계약업체·제조사, 물품규격명·물품식별번호로 검색할 수 있다.
- 공식 `getShoppingMallPrdctInfoList`에 기존 서비스키와 `inqryDiv=1`을 전달한다. 기간은 `rgstDt` 기준이며 한국 시간으로 어제까지 수집한다. 식품 판정과 품명 묶음은 매출 조회와 공유한다. [조달청 API 명세](https://www.data.go.kr/data/15129471/openapi.do)
- `POST /api/registrations/sync`는 `startDate`, `endDate`, `category`, `step`, `force`를 받는다. 날짜 형식은 YYYYMMDD다. 한 페이지씩 저장하며 중단 시 같은 기간·분류로 재개한다. 앱 시작 시 생성하는 `registration_batches`와 `registration_pages`에 저장한다.
- 동기화 응답은 현재 기간·페이지, 전체 페이지, 원천 누적/전체 건수, 해당 페이지 원천·식품 건수를 포함한다. 품목등록 화면은 이를 진행률 막대와 페이지별 수집 내역으로 계속 표시한다.
- `GET /api/registrations`는 같은 기간·분류에 `company`, `productName`, `page`, `pageSize`를 추가로 받는다. 응답의 `through`는 실제 조회 종료일이다. 수집이 필요한 경우 `complete=false`, `total=null`을 반환한다. 수집 완료 후 조건에 맞는 행이 없으면 `total=0`이다.
- `GET /api/registrations/excel`은 화면과 같은 기간·분류·업체·제품 필터로 `품목등록정제`, `품목등록원천`, `월별등록집계` 시트를 만든다. 정제 시트는 매출 엑셀과 같은 제품명·규격 분리 규칙을 사용하며 물품식별번호는 텍스트로 보존한다.
- 로컬 실데이터 검증에서 2026년 11월 1~11일 원천 68,466건(69페이지) 중 식품 382건을 저장했다. 이 중 식육가공품 105건은 품명을 지정해 별도로 수집한 API 응답과 모든 행이 일치했다. 2026년 7월 식육가공품은 317건, 2025년 냉동감자 연간 조회는 6건이었다.
- 페이지 진행 화면은 2026년 7월 31일 원천 4,216건을 강제 재수집해 1/5부터 5/5까지 순서대로 표시되는 것을 브라우저에서 확인했다. 품목등록 엑셀은 2026년 11월 1~11일 정제 382행·원천 382행·월별 합계 382건과 식육가공품 필터 105건을 대조했다.
- 검증 명령은 `python -m unittest discover -s backend/tests -v`와 `npm run build`다. 백엔드 테스트 12개와 프런트엔드 운영 빌드가 통과했다. Render는 `master` 브랜치를 자동 배포하며 운영 주소는 아래 배포 항목과 같다.

## 2026-11-11 운영 배포

- 운영 주소는 https://mas-market-shares.onrender.com 이다. Render 무료 웹 서비스가 React 화면과 FastAPI를 함께 제공하며, 배포 커밋 `a8a3177`이 live 상태가 된 것을 확인했다.
- 웹 로그인 계정은 `mas`이며 비밀번호는 Render 환경 변수 `MAS_PASSWORD`에 설정한다. 담당 PC에서는 프로젝트 루트의 Git 제외 파일 `.env`에서 확인할 수 있다.
- 운영 데이터는 Neon 프로젝트 `blue-morning-40075101`의 `production` 브랜치에 저장한다. SQLite에서 테이블 6개를 이전하고 행 수를 대조했다. 이전 직후 앱 조회 코드로 확인한 2026년 7월 순액은 46,566,215,690원이다.
- 로컬 배포 구성에서 인증 차단과 로그인 후 화면 응답을 검증했다. 운영 주소에서의 인증 후 7월 조회와 XLSX 다운로드는 배포 당시 미검증 상태다.

## 2026-11-11 추가 기능

- 기존 엑셀 다운로드 API에 `월별정제매출` 시트를 추가했다. 업체별, 업체별품목, 품목별, 식품원천내역, 월별정제매출, 월별집계 순서다.
- 필터를 통과한 원천 행에서 업체·세부품명·물품식별번호·제품명·규격·접수월별 순액을 집계한다. 음수 정정분을 포함하고 `incdecAmt`가 비어 있으면 `prdctAmt`를 사용한다.
- 월별 합계에 10/11을 곱한 부가세 별도 금액을 저장한다. 엑셀의 원 단위 반올림은 표시 형식만 적용한다. 규격 경계를 판정할 수 없는 물품규격명은 전체를 제품명에 보존한다.
- 새 테스트는 `backend/tests/test_monthly_clean_sales.py`에 있다.

작성일 2026-11-10

## 오늘 완료한 작업

- 조달청 나라장터쇼핑몰 납품요구상세 API를 식품 전용 수집 경로로 재작성했다.
- 물품분류번호가 `50`으로 시작하는 행만 저장하고 `5021`으로 시작하는 담배 분류는 제외한다.
- 식품명 또는 세부품명을 API 요청에 전달할 수 있게 했다.
- API 응답의 전체 건수와 페이지 번호를 확인하면서 마지막 페이지까지 순회한다.
- 페이지별 원천 JSON과 다음 페이지 커서를 SQLite에 저장한다. 중단 뒤 같은 조건으로 DB 동기화를 다시 실행하면 마지막 저장 페이지부터 이어받는다.
- 완료된 기간은 재수집하지 않는다. 최신 정정분이 필요하면 화면의 `완료 자료도 다시 수집`을 선택한다.
- 업체별, 업체별 품목, 품목별, 월별 집계, 식품 원천 내역을 엑셀로 저장한다.
- 식품 버튼의 중복 코드 문제를 제거했다. 품명과 세부품명은 개별 선택 상태를 사용한다.
- 일·월·년·직접 지정 기간을 지원한다.

## 실행 방법

### 백엔드

```powershell
cd C:\Users\케이지에프앤비\Documents\ChatGPT\MAS_market_shares\backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item ..\.env.example .env
# .env에 OPEN_API_SERVICE_KEY 또는 G2B_SERVICE_KEY를 설정
$env:PYTHONPATH = (Get-Location).Path
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

### 프론트엔드

```powershell
cd C:\Users\케이지에프앤비\Documents\ChatGPT\MAS_market_shares\frontend
npm install
npm run dev -- --host 127.0.0.1
```

브라우저에서 `http://127.0.0.1:5173/`을 연다. 백엔드 상태는 `http://127.0.0.1:8000/api/health`에서 확인한다.

## 화면 사용 순서

1. 기간 단위에서 일·월·년 또는 직접 지정을 선택한다.
2. 전체 또는 식품 버튼을 선택한다. 전체 식품을 먼저 수집하면 실제 API가 반환한 품명·세부품명 목록이 추가로 표시된다.
3. `DB 동기화`를 누른다. 진행률에 현재 날짜 구간, 페이지, 원천 확인 건수가 표시된다.
4. 완료 메시지를 확인한 뒤 `조회`를 누른다.
5. 업체명과 제품명은 완료된 식품 DB 안에서 부분 검색한다.
6. `엑셀 다운로드`에는 업체별, 업체별품목, 품목별, 월별집계, 식품원천내역 시트가 들어간다.

## API 흐름

`POST /api/dashboard/sync`는 `startDate`, `endDate`, `category`, `step`, `force`를 받는다. 화면은 `step=true`로 한 페이지씩 요청하고 `complete=true`가 될 때까지 반복한다. API 호출 한도에 도달하거나 일시 오류가 발생하면 저장된 `next_page`부터 재개한다.

`GET /api/dashboard`는 같은 기간과 식품 조건으로 저장된 원천을 집계한다. 업체별 금액과 업체별 품목 금액은 `incdecAmt`를 우선 사용하고 값이 없으면 `prdctAmt`를 사용한다. `dlvrReqRcptDate`를 접수일 기준으로 사용한다.

`GET /api/dashboard/excel`은 같은 조건의 집계와 원천 내역을 파일로 만든다. 대량 자료는 xlsxwriter constant-memory 모드로 작성한다.

## 데이터 모델

- `food_batches`는 날짜 구간, 식품 조건, 다음 페이지, 확인 건수, API 전체 건수, 완료 여부를 저장한다.
- `food_pages`는 배치별 페이지 번호와 식품 원천 행 JSON을 저장한다.
- `api_daily_usage`는 당일 API 호출 수를 저장한다.
- 이전 기능의 테이블인 `g2b_cached_rows`, `raw_deliveries`, `query_cache`는 기존 데이터 호환을 위해 모델에 남아 있다. 새 식품 대시보드는 `food_batches`와 `food_pages`를 사용한다.

## 검증 기록

- 2026년 7월 전체 조회는 조달청 원천 242,868건, 244페이지를 끝까지 확인했다.
- 저장된 식품 행은 13,788건이며 비식품 행은 0건이었다.
- 2026년 7월 전체 식품은 업체 437곳, 품목 2,997개, 순액 46,566,215,690원이었다.
- 2026년 7월 식육가공품은 원천 2,175건, 업체 158곳, 품목 727개, 순액 17,707,101,818원이었다.
- 2026년 7월 15일 하루 식육가공품 조회는 84건, 업체 36곳, 순액 609,888,590원이었다.
- 2025년 냉동감자 연간 조회에서 12개월 구간을 처리했다.
- 단위 테스트는 `backend/tests`에서 재개, 호출 한도, API 오류, 식품 필터, 윤년, 0건 응답, 엑셀 시트를 검증한다.

## 테스트 명령

```powershell
$env:PYTHONPATH = "C:\Users\케이지에프앤비\Documents\ChatGPT\MAS_market_shares\backend"
python -m unittest discover -s backend/tests
python -m py_compile backend/app/*.py backend/app/services/*.py
cd frontend
npm run build
```

## 주의사항

- 서비스키는 커밋하지 않는다. `.env`는 로컬 설정으로만 사용한다.
- API 호출 수는 날짜 단위로 기록된다. 전체 연도나 대규모 기간은 여러 번 나누어 동기화할 수 있다.
- 식품명 검색 API는 공식 `prdctClsfcNoNm` 또는 `dtilPrdctClsfcNoNm`을 사용한다. 사업상 묶음인 `장류`, `축산가공품`, `빵류`, `과자류` 등은 저장된 공식 품명과 세부품명을 조합해 필터링한다.
- 집계가 완료되지 않은 기간은 조회하지 않는다. 화면에 수집 필요 메시지가 나오면 DB 동기화를 다시 실행한다.
- `exports/`는 검증 산출물 디렉터리이며 저장소 커밋 대상에서 제외했다.

## 다음 작업 후보

- 식품 분류 묶음의 업무 정의를 담당자와 확정한다.
- API 전체 기간 수집을 자동 예약할 경우 일일 호출 한도와 저장 용량을 먼저 정한다.
- 완료 배치의 최신 정정분만 비교 수집하는 증분 동기화를 추가한다.
