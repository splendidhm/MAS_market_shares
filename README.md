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

## 주요 API
- `GET /api/dashboard/market-share`
- `GET /api/dashboard/market-share/excel`
- `GET /api/health`

## 참고
- 기본값으로 `use_dummy=true`를 보내면 더미데이터 기반으로 UI를 테스트할 수 있습니다.
- 동일 조건 조회 시 캐시 테이블을 우선 사용합니다.
