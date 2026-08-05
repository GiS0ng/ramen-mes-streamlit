# 라면 MES

Python, Streamlit, SQLite로 구현한 라면 제조 실행 시스템(MES) 데모입니다.

## 주요 기능

- 생산 현황 대시보드와 현재 완제품 재고
- 설비별 최근 생산 수율 및 불량 코드 분석
- 품목 합계 기준 원재료 안전재고 경보
- 구매·입고, 생산계획 기반 설비 가동, 품질, 출하 관리
- 완제품 1개당 라면 면·제품별 맛 스프·제품별 맛 포장지 낱개 LOT 1:1:1 투입
- 박스 1개당 완제품 낱개 LOT 40개 추적
- 원재료·완제품·박스·고객 기준 양방향 LOT 추적

## 프로젝트 구조

```text
app.py             Streamlit 초기화와 멀티페이지 라우팅
pages/             대시보드 등 7개 업무 화면
services/          등록 검증과 업무 트랜잭션
repositories/      화면용 데이터 조회
domain/rules.py    박스 수량·안전재고 등 공통 업무 규칙
ui/components.py   표·선택·처리 메시지 공통 UI
db.py              SQLite 연결과 기본 데이터 접근
seed.py            재현 가능한 데모 데이터 생성
schema.sql         테이블·뷰·트리거 스키마
```

화면 이동은 Streamlit의 `st.Page`와 `st.navigation`을 사용합니다. `app.py`는 공통 요소만 실행하고 선택된 `pages/*.py` 화면을 라우팅합니다.

## 로컬 실행

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

## 테스트

```bash
pip install -r requirements-dev.txt
python -m pytest -v
```

테스트는 임시 SQLite 데이터베이스를 사용하므로 로컬 `data/mes.db`를 변경하지 않습니다. 업무 규칙, 입고부터 출하까지의 통합 흐름, 8개 Streamlit 페이지 로드를 검사합니다.

## Streamlit Community Cloud

저장소를 Streamlit Community Cloud에 연결하고 엔트리 파일로 `app.py`를 선택합니다. 배포 환경에 DB 파일이 없으면 최신 더미 데이터가 자동으로 생성됩니다.

Community Cloud의 로컬 파일 저장은 영구 보존되지 않으므로 이 배포는 시연용입니다. 서버 재시작이나 재배포 시 사용자가 입력한 데이터가 초기화될 수 있습니다.
