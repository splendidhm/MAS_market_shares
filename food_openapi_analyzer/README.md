# 공공조달 OpenAPI 기반 식품류 월별 조달실적 자동 분석 시스템

## 1) 목적
조달청 OpenAPI를 사용해 식품류 카테고리의 월별 조달 실적을 수집/집계하고, 엑셀로 저장합니다.

## 2) 파일 구조
```
food_openapi_analyzer/
├─ api_client.py         # OpenAPI 호출(페이지네이션/예외처리)
├─ food_filter.py        # 식품 카테고리 코드 로드/자동 매핑
├─ data_processor.py     # pandas 집계 로직
├─ export_excel.py       # 엑셀 저장
├─ main.py               # 실행 엔트리포인트
├─ requirements.txt
├─ .env.example
└─ config/
   └─ food_category_codes.json
```

## 3) 설치
```bash
pip install -r requirements.txt
```

## 4) 환경변수 설정
`.env.example`를 `.env`로 복사 후 값 입력:
```env
SERVICE_KEY=발급받은_공공데이터_API_키
BASE_URL=http://apis.data.go.kr/1230000/at/PubPrcrmntStatInfoService
OPERATION=getPrdctIdntNoServcAccotArslt
REQUEST_SLEEP_SECONDS=0.2
```

## 5) 식품 코드 설정
`config/food_category_codes.json`에서 카테고리별 품목코드를 입력하세요.

- 코드가 빈 경우, 프로그램이 응답 데이터(`prdctNm`, `prdctClCd`) 기반으로 자동 매핑을 시도합니다.
- 자동 매핑이 실패하면 해당 카테고리는 조회에서 제외됩니다.

## 6) 실행
```bash
python main.py
```
실행 후 시작년월/종료년월을 `YYYYMM` 형식으로 입력합니다.

## 7) 출력
- 콘솔: 월별 합계, 품목별 합계
- 엑셀: `food_procurement_YYYYMM.xlsx`
  - 시트1 `원본데이터`
  - 시트2 `월별집계` (월합계 + 피벗)
  - 시트3 `품목별집계`

## 8) 확장 포인트
- 업체별/수요기관별/MAS 분석 컬럼 추가
- Streamlit 대시보드 연동
- Plotly 시각화 자동 생성
