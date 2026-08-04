from __future__ import annotations

import streamlit as st

import db
from ui.components import run_action


st.set_page_config(page_title="라면 MES", page_icon="🏭", layout="wide")

database_was_missing = not db.DB_PATH.exists()
db.initialize()
if database_was_missing:
    db.seed_demo()

st.markdown(
    """
    <style>
    .block-container{padding-top:1.6rem}.stMetric{background:#f7f9fc;border:1px solid #e7ebf0;
    border-radius:12px;padding:12px}.subtitle{color:#607080;margin-top:-12px;margin-bottom:18px}
    </style>
    """,
    unsafe_allow_html=True,
)

pages = {
    "생산 관리": [
        st.Page("pages/dashboard.py", title="생산현황 대시보드", icon="🏭", default=True),
        st.Page("pages/production_quality.py", title="생산 등록·품질 관리", icon="⚙️"),
        st.Page("pages/equipment.py", title="설비 성과", icon="📊"),
    ],
    "자재·물류": [
        st.Page("pages/purchasing.py", title="구매·입고 관리", icon="📦"),
        st.Page("pages/shipping.py", title="출하 관리", icon="🚚"),
        st.Page("pages/traceability.py", title="LOT 양방향 추적", icon="🔍"),
    ],
    "시스템": [
        st.Page("pages/master_data.py", title="기준정보 관리", icon="🗂️"),
    ],
}

navigation = st.navigation(pages, position="sidebar")

with st.sidebar:
    st.divider()
    st.caption("SQLite · LOT 기반 재고 · 트리거 자동 차감")
    st.info("공개 데모 환경입니다. 서버 재시작 또는 재배포 시 입력 데이터가 초기화될 수 있습니다.")
    if st.button("더미 데이터 생성", type="primary", width="stretch"):
        run_action(db.seed_demo, "현재 월을 포함한 최근 3개월의 더미 데이터를 생성했습니다.")
    if st.button("데모 데이터 초기화", width="stretch"):
        run_action(db.reset_demo, "데이터베이스를 초기화했습니다.")

navigation.run()
