# 라면 MES

Python, Streamlit, SQLite로 구현한 라면 제조 실행 시스템(MES) 데모입니다.

## 주요 기능

- 생산 현황 대시보드와 현재 완제품 재고
- 설비별 최근 생산 수율 및 불량 코드 분석
- 품목 합계 기준 원재료 안전재고 경보
- 구매·입고, 생산 등록, 품질, 출하 관리
- 완제품 1개당 면·스프·포장지 낱개 LOT 1:1:1 투입
- 박스 1개당 완제품 낱개 LOT 40개 추적
- 원재료·완제품·박스·고객 기준 양방향 LOT 추적

## 로컬 실행

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

## Streamlit Community Cloud

저장소를 Streamlit Community Cloud에 연결하고 엔트리 파일로 `app.py`를 선택합니다. 배포 환경에 DB 파일이 없으면 최신 더미 데이터가 자동으로 생성됩니다.

Community Cloud의 로컬 파일 저장은 영구 보존되지 않으므로 이 배포는 시연용입니다. 서버 재시작이나 재배포 시 사용자가 입력한 데이터가 초기화될 수 있습니다.
