from __future__ import annotations

import streamlit as st

from repositories import equipment as equipment_repository
from services import production
from ui.components import run_action, select_id, show_frame


st.title("설비")
operation_tab, result_tab = st.tabs(["생산계획 가동", "성과 조회"])

@st.fragment(run_every="10s")
def operation_panel() -> None:
    try:
        production.auto_complete_due_plans()
    except RuntimeError as exc:
        st.warning(str(exc))
    st.caption(
        "페이지 접속 시 경과시간만큼 생산량을 반영합니다. 이 화면을 열어 둔 동안에는 "
        "10초마다 진행 수량과 완제품 재고를 갱신합니다."
    )

    st.subheader("가동 대기 생산계획")
    planned = equipment_repository.plans("PLANNED")
    if planned.empty:
        st.info("가동 대기 중인 생산계획이 없습니다.")
    else:
        show_frame(planned, height=250)

    start_options = equipment_repository.plan_options(
        "PLANNED", available_only=True
    )
    if start_options:
        start_plan_id = select_id(
            "가동을 시작할 생산계획서*", start_options, "equipment_start_plan"
        )
        if st.button("설비 가동 시작", type="primary") and start_plan_id:
            run_action(
                lambda: production.start_plan(start_plan_id),
                "생산계획 가동을 시작했습니다.",
            )
    elif not planned.empty:
        st.warning("가동 가능한 설비에 배정된 생산계획이 없습니다.")

    st.divider()
    st.subheader("가동 중 생산계획")
    running = equipment_repository.plans("IN_PROGRESS")
    if running.empty:
        st.info("현재 가동 중인 생산계획이 없습니다.")
    else:
        st.markdown("#### 가동 완료 계획 일시")
        show_frame(
            running[[
                "계획번호", "설비", "품목", "계획수량",
                "생산완료수량", "잔여계획수량", "가동완료계획일시",
            ]],
            height=min(220, 38 + len(running) * 35),
        )
        st.markdown("#### 가동 계획 상세")
        show_frame(running, height=220)
        st.caption(
            "설비 생산능력과 경과시간에 맞춰 계획 잔량이 감소하고 완제품 재고가 "
            "증가합니다. 완제품 40개가 모이면 박스가 자동 생성됩니다."
        )

    st.divider()
    st.subheader("설비 가동 상태")
    show_frame(equipment_repository.equipment_status(), height=240)


with operation_tab:
    operation_panel()

with result_tab:
    st.subheader("설비별 누적 성과")
    show_frame(equipment_repository.performance(), height=260)

    st.subheader("생산계획 기준 가동 실적")
    history = equipment_repository.operation_history()
    if history.empty:
        st.info("등록된 설비 가동 실적이 없습니다.")
    else:
        show_frame(history, height=340)
