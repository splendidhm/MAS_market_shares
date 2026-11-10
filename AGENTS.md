# AGENTS.md

## 프로젝트 목적

이 저장소는 조달청 나라장터쇼핑몰 공공데이터에서 식품류 납품요구 데이터를 수집하고, 업체별·품목별 매출과 시장점유율을 조회하며 엑셀로 저장하는 내부 도구다. 식품 외 카테고리는 제품 범위에서 제외한다.

## 저장소 규칙

- 서비스키, `.env` 파일, 개인 데이터베이스를 커밋하지 않는다.
- `exports/`의 검증용 엑셀은 커밋하지 않는다.
- `frontend/node_modules`와 Vite 캐시는 빌드 산출물이다. 소스 변경 커밋에 포함하지 않는다.
- 기존 사용자 변경이 있는 파일은 덮어쓰지 말고 먼저 `git status`와 diff를 확인한다.
- API 응답을 수정하거나 필터를 추가할 때는 실제 API 응답 필드명을 확인한다.

## 구조

### 백엔드

- `backend/app/main.py`는 FastAPI 앱과 CORS, 시작 시 테이블 생성을 등록한다.
- `backend/app/routers/dashboard.py`는 대시보드, 동기화, 사용량, 엑셀 API 라우터를 등록한다.
- `backend/app/services/g2b_api.py`는 조달청 HTTP 요청을 담당한다. `fetch_page`는 페이지 번호와 페이지 크기, 전체 건수, 반환 건수를 검증한다.
- `backend/app/services/food_report.py`는 식품 판정, 날짜 구간 분할, 페이지 재개, 품명 필터, 업체별·품목별 집계를 담당한다.
- `backend/app/services/excel_exporter.py`는 대량 행을 메모리 제한 방식으로 업체별·품목별·월별·원천 시트에 작성한다.
- `backend/app/models.py`의 `FoodBatch`와 `FoodPage`가 새 식품 수집기의 영속 상태다.
- `backend/app/services/quota_service.py`는 날짜별 API 호출 수를 기록한다.

### 프론트엔드

- `frontend/src/App.jsx`는 필터 상태, 단계별 동기화, 집계 표시, 품목별 표를 관리한다.
- `frontend/src/components/Filters.jsx`는 일·월·년 기간 선택과 식품 버튼, 직접 품명 입력을 담당한다.
- `frontend/src/api/dashboardApi.js`는 백엔드 URL과 조회·동기화·엑셀 요청을 한곳에서 관리한다.
- `frontend/src/components/MarketShareTable.jsx`와 `TopManufacturersChart.jsx`는 업체별 집계를 표시한다.

## 식품 범위

기본 식품 판정은 `prdctClsfcNo`가 `50`으로 시작하는지 확인하고 `5021`으로 시작하는 담배 분류를 제외한다. 이 규칙은 API 응답 필터와 DB 저장 전에 적용한다. 식품 버튼은 표시용 코드가 서로 같아도 라벨을 상태값으로 사용해 서로 독립적으로 동작한다.

공식 필터는 다음 API 필드를 사용한다.

- 품명은 `prdctClsfcNoNm`
- 세부품명은 `dtilPrdctClsfcNoNm`
- 물품규격명은 `prdctIdntNoNm`
- 품목분류번호는 `prdctClsfcNo`

`식육가공품`, `김치`, `장류` 같은 업무용 묶음은 `food_report.py`의 `GROUPS`에 정의한다. 새로운 묶음은 임의 코드보다 실제 API가 반환한 품명·세부품명에 근거해 추가한다.

## 수집 불변조건

페이지 저장과 배치 커서 변경은 한 트랜잭션으로 처리한다. `next_page`는 마지막으로 저장한 페이지보다 하나 커야 한다. `scanned`는 저장한 원천 페이지의 행 수 합계여야 한다. `expected`는 API `totalCount`와 같아야 한다. 완료는 `scanned == expected`일 때만 true로 설정한다.

API 응답의 `pageNo`, `numOfRows`, `totalCount`, 실제 `items` 길이를 검증한다. 검증 실패 시 다음 페이지로 넘어가지 않는다. 동일 조건으로 재시도할 수 있는 오류는 현재 페이지를 유지한다. 인증 오류는 401, 호출 한도는 429, 반복된 API 오류는 502로 반환한다.

날짜는 `dlvrReqRcptDate` 접수일을 기준으로 한다. 월·연도 조회는 달 경계로 날짜 구간을 나누고, 윤년 2월을 포함한 실제 달력 마지막 날을 사용한다.

금액은 `incdecAmt`를 우선 사용한다. 해당 값이 없을 때 `prdctAmt`를 사용한다. 변경·취소 행의 음수 금액을 합계에 포함하므로 증감 순액을 표시한다.

## API 계약

`POST /api/dashboard/sync`

- 입력: `startDate`, `endDate`, `category`, `step`, `force`
- `step=true`는 한 페이지 처리 후 진행률을 반환한다.
- 응답의 `complete`가 false이면 같은 입력으로 다시 호출한다.

`GET /api/dashboard`

- 입력: `startDate`, `endDate`, `category`, `company`, `productName`
- 완료된 배치만 집계한다.
- 주요 결과는 `total_amount`, `company_rank`, `item_rows`, `chart_data`, `categories`다.

`GET /api/dashboard/excel`

- 대시보드와 같은 입력을 사용한다.
- 업체별, 업체별품목, 품목별, 식품원천내역, 월별정제매출, 월별집계 순으로 반환한다. 월별정제매출만 부가세 별도(원천 증감 순액 ÷ 1.1)이며, 조회한 월을 빠짐없이 표시한다.

`GET /api/dashboard/usage`

- 당일 호출 수, 일일 한도, 남은 호출 수를 반환한다.

## 검증 방법

변경 후 다음 순서로 확인한다.

1. `python -m unittest discover -s backend/tests`
2. `python -m py_compile backend/app/*.py backend/app/services/*.py`
3. `npm run build`를 실행한다.
4. 서비스키가 설정된 로컬 서버에서 `/api/health`를 호출한다.
5. 하루 범위, 한 달 범위, 연간 범위, 연도 경계 범위를 각각 동기화한다.
6. DB의 배치 `expected`, `scanned`, `complete`와 API 진행률을 비교한다.
7. 대시보드 합계, 업체별 합계, 품목별 합계, 엑셀 원천 행의 합계를 비교한다.
8. 식품 외 품목분류번호가 저장되지 않는지 확인한다.

## 실행 명령

백엔드는 `backend`를 작업 디렉터리로 사용하고 `uvicorn app.main:app --reload --host 127.0.0.1 --port 8000`으로 실행한다. 프론트엔드는 `frontend`에서 `npm run dev -- --host 127.0.0.1`으로 실행한다. 서비스키는 `.env`의 `G2B_SERVICE_KEY`, `SERVICE_KEY`, `OPEN_API_SERVICE_KEY` 중 현재 설정 방식에 맞는 변수를 사용한다.

## 변경 시 주의

- 수집 API를 다른 오퍼레이션으로 바꾸려면 요청 변수, 날짜 의미, 금액 의미, 페이지 응답 구조를 공식 명세와 실제 응답으로 함께 검증한다.
- 월별 캐시를 단순히 행 수가 0보다 크다는 이유로 완료 처리하지 않는다.
- 조회 결과가 없을 때 API 동기화가 완료되지 않은 상태와 완료 후 실제 0건인 상태를 구분한다.
- 업체 검색을 추가할 때 시장 전체 분모와 선택 업체 금액의 의미를 유지한다.
- 엑셀에 전체 원천 행을 추가할 때 메모리 사용량과 Excel 행 한도를 고려한다.
- 커밋 전 `git status --short`, `git diff --check`, 테스트 결과를 확인한다.
