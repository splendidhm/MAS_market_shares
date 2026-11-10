# MAS Market Shares Dashboard

조달청 공공데이터 Open API를 이용해 식품 품목의 월별 납품금액을 조회하고 제조사 점유율을 분석하는 내부 대시보드 프로젝트입니다.

## 기술 스택
- Backend: FastAPI + Pandas + SQLite(SQLAlchemy)
- Frontend: React + Tailwind + Recharts
- Export: xlsxwriter

## 프로젝트 구조
```
MAS_market_shares/
├─ backend/
│  ├─ app/
│  │  ├─ core/
│  │  ├─ routers/
│  │  ├─ services/
│  │  ├─ main.py
│  │  ├─ models.py
│  │  └─ schemas.py
│  └─ requirements.txt
├─ frontend/
│  ├─ src/
│  │  ├─ api/
│  │  ├─ components/
│  │  ├─ App.jsx
│  │  ├─ main.jsx
│  │  └─ index.css
│  └─ package.json
└─ .env.example
```

## 백엔드 실행
1. 가상환경 생성/활성화
2. 의존성 설치
   - `pip install -r backend/requirements.txt`
3. `.env.example`를 복사해 `.env` 생성 후 서비스키 입력
4. 실행
   - `uvicorn app.main:app --reload --host 0.0.0.0 --port 8000`
   - 실행 위치: `backend`

## 프론트엔드 실행
1. `frontend` 폴더 이동
2. `npm install`
3. `npm run dev`

## 식품 조회와 동기화

기간 단위에서 일·월·년 또는 직접 지정을 선택한다. 전체는 나라장터 식품 대분류(물품분류번호 50으로 시작하며 담배 분류 5021 제외)를 조회한다. 품명, 세부품명 버튼 또는 직접 입력으로 범위를 좁힐 수 있다. 전체 식품을 한 번 조회하면 실제 수집된 공식 분류도 목록에서 선택할 수 있다.

DB 동기화는 조달청 납품요구상세를 접수일 기준으로 조회한다. 달 경계에서 기간을 나누며 반환된 페이지 번호·건수·전체 건수를 확인한다. 식품명 조회는 서비스가 지원하는 품명 또는 세부품명 변수를 사용한다. 전체 및 여러 분류를 합친 버튼은 전체 페이지를 읽고 식품 원천 행만 저장한다. 원천의 변경·취소는 증감금액을 접수일에 반영하며 증감금액 미제공 시 물품금액을 사용한다.

각 페이지와 다음 페이지 번호를 한 트랜잭션에 저장한다. 한도 소진 또는 연결 중단 후 같은 조건으로 동기화를 누르면 이어받는다. 완료된 기간은 재사용한다. 최신 정정분은 ‘완료 자료도 다시 수집’으로 갱신한다. 예전 100건 샘플은 새 수집의 완료 판단에 사용하지 않는다.

조회 및 엑셀은 완전히 받은 기간을 사용한다. 엑셀에 업체별, 업체별품목, 품목별, 월별집계, 식품원천내역 시트를 저장한다. 원천 시트는 API 필드를 보존한다.

- `POST /api/dashboard/sync`에 `startDate`, `endDate`(YYYYMMDD), `category`를 전달한다. 화면은 `step=true`로 한 페이지씩 진행률을 받는다.
- `GET /api/dashboard`와 `GET /api/dashboard/excel`은 같은 기간, 품목, 업체명 및 제품명 조건을 사용한다.
- `GET /api/dashboard/usage`에서 앱의 일일 사용량을 확인한다.
