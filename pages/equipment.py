from __future__ import annotations

import streamlit as st

import db
from services import equipment as equipment_service
from ui.components import grid, run_action, select_id


st.title("설비 성과")
register_tab, result_tab = st.tabs(["가동 실적 등록", "성과 조회"])
equipment = db.options("SELECT equipment_id,equipment_code||' · '||equipment_name FROM equipment WHERE is_active='Y'")
productions = db.options("SELECT production_id,production_no FROM production ORDER BY production_date DESC")

with register_tab:
    with st.form("operation"):
        c1, c2, c3 = st.columns(3)
        equipment_id = select_id("설비*", equipment, "op_eq")
        production_id = select_id("생산번호", productions, "op_prod")
        operation_date = c3.date_input("가동일")
        c4, c5, c6 = st.columns(3)
        planned = c4.number_input("계획 시간(분)", min_value=0, step=10)
        running = c5.number_input("가동 시간(분)", min_value=0, step=10)
        downtime = c6.number_input("비가동 시간(분)", min_value=0, step=10)
        reason = st.text_input("비가동 사유")
        if st.form_submit_button("가동 실적 등록", type="primary") and equipment_id:
            run_action(
                lambda: equipment_service.register_operation(
                    equipment_id,
                    production_id,
                    operation_date.isoformat(),
                    planned,
                    running,
                    downtime,
                    reason,
                ),
                "설비 가동 실적을 등록했습니다.",
            )

with result_tab:
    grid("""SELECT e.equipment_code 설비코드,e.equipment_name 설비명,COALESCE(SUM(eo.planned_minutes),0) 계획시간,
    COALESCE(SUM(eo.running_minutes),0) 가동시간,COALESCE(SUM(eo.downtime_minutes),0) 비가동시간,
    ROUND(SUM(eo.running_minutes)*100.0/NULLIF(SUM(eo.planned_minutes),0),2) 가동률
    FROM equipment e LEFT JOIN equipment_operation eo USING(equipment_id) GROUP BY e.equipment_id ORDER BY e.equipment_code""")
