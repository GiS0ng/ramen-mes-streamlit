from __future__ import annotations

from datetime import date
from math import ceil

import streamlit as st

import db
from repositories import production_quality as quality_repository
from services import production
from ui.components import grid, run_action, select_id, show_frame


st.title("생산 등록·품질 관리")
plan_tab, production_tab, material_tab, defect_tab = st.tabs(
    ["생산 계획서", "생산 등록", "원재료 투입", "불량 등록"]
)

products = db.options(
    """SELECT item_id,item_code||' · '||item_name
       FROM item WHERE item_type='PRODUCT' AND is_active='Y'
       ORDER BY item_name"""
)
equipment = db.options(
    """SELECT equipment_id,equipment_code||' · '||equipment_name||
              ' · 분당 '||capacity_per_minute||'개'
       FROM equipment WHERE is_active='Y'
       ORDER BY equipment_code"""
)
productions = db.options(
    """SELECT production_id,production_no||' · '||i.item_name
       FROM production p JOIN item i USING(item_id)
       WHERE p.status<>'CANCELED' ORDER BY production_date DESC"""
)

with plan_tab:
    st.subheader("생산 계획서 작성")
    with st.form("production_plan"):
        c1, c2, c3 = st.columns(3)
        with c1:
            plan_equipment_id = select_id("설비*", equipment, "plan_equipment")
        with c2:
            plan_product_id = select_id("품목*", products, "plan_product")
        plan_quantity = c3.number_input(
            "생산수량*", min_value=1, step=1, value=1000
        )
        if plan_equipment_id:
            capacity = db.query(
                "SELECT capacity_per_minute FROM equipment WHERE equipment_id=?",
                (plan_equipment_id,),
            )[0][0]
            expected_minutes = ceil(plan_quantity / capacity)
            st.caption(
                f"분당 {capacity:,.0f}개 기준 예상 포장시간: "
                f"{expected_minutes:,}분 ({expected_minutes / 60:,.1f}시간)"
            )
        if (
            st.form_submit_button("생산 계획 등록", type="primary")
            and plan_equipment_id
            and plan_product_id
        ):
            run_action(
                lambda: production.create_plan(
                    plan_equipment_id, plan_product_id, int(plan_quantity)
                ),
                "생산 계획서를 등록했습니다.",
            )

    st.subheader("생산 계획 목록")
    plans = quality_repository.production_plans()
    if plans.empty:
        st.info("등록된 생산 계획이 없습니다.")
    else:
        show_frame(plans, height=300)

with production_tab:
    with st.form("production"):
        c1, c2, c3, c4 = st.columns(4)
        request_no = c1.text_input("생산요청번호*", value=f"REQ-{date.today():%Y%m%d}-")
        with c2:
            item_id = select_id("제품*", products, "prod_item")
        quantity = c3.number_input("요청수량*", min_value=1, step=1, value=1000)
        with c4:
            equipment_id = select_id("포장 설비", equipment, "prod_eq")
        production_date = st.date_input("생산일")
        st.caption(
            "완제품 1개당 낱개 LOT 1개와 면·제품별 스프·제품별 포장지 LOT가 "
            "각각 1개씩 투입됩니다. 40개마다 박스 1개가 생성됩니다."
        )
        if st.form_submit_button("생산 및 완제품 LOT 등록", type="primary") and item_id:
            run_action(
                lambda: production.create_request(
                    request_no, item_id, equipment_id,
                    production_date.isoformat(), int(quantity),
                ),
                f"생산요청 {int(quantity):,}개와 낱개 LOT를 등록했습니다.",
            )
    grid(
        """SELECT production_no 생산번호,item_name 제품,lot_no 완제품LOT,
                  production_date 생산일,input_qty 투입량,p.qty 생산량,p.status 상태
           FROM production p JOIN item i ON i.item_id=p.item_id
           JOIN lot l ON l.lot_id=p.output_lot_id
           ORDER BY production_date DESC"""
    )

with material_tab:
    raw_lots = db.options(
        """SELECT lot_id,lot_no||' · '||i.item_name||' (재고 '||l.qty||')'
           FROM lot l JOIN item i USING(item_id)
           WHERE lot_type='RECEIPT' AND qty>0
           ORDER BY expire_date,received_date"""
    )
    with st.form("material"):
        c1, c2, c3 = st.columns(3)
        with c1:
            production_id = select_id("생산번호*", productions, "mat_prod")
        with c2:
            lot_id = select_id("원재료 LOT*", raw_lots, "mat_lot")
        quantity = c3.number_input("사용량*", min_value=0.01)
        if st.form_submit_button("원재료 투입", type="primary") and production_id and lot_id:
            run_action(
                lambda: production.register_material(production_id, lot_id, quantity),
                "원재료 투입 및 재고 차감을 완료했습니다.",
            )
    grid(
        """SELECT p.production_no 생산번호,i.item_name 원재료,l.lot_no LOT,
                  pm.qty 사용량,pm.created_at 등록시각
           FROM production_material pm JOIN production p USING(production_id)
           JOIN lot l ON l.lot_id=pm.material_lot_id JOIN item i USING(item_id)
           ORDER BY pm.created_at DESC"""
    )

with defect_tab:
    st.subheader("생산실적 조회 기반 불량 등록")
    filter_c1, filter_c2 = st.columns(2)
    with filter_c1:
        defect_equipment_id = select_id("불량 발생 설비*", equipment, "defect_equipment")

    available_dates = (
        quality_repository.production_dates(defect_equipment_id)
        if defect_equipment_id else []
    )
    with filter_c2:
        selected_production_date = st.selectbox(
            "생산일자*",
            available_dates,
            disabled=not available_dates,
            placeholder="생산실적이 있는 일자를 선택하세요",
        )

    lot_options = (
        quality_repository.production_lot_options(
            defect_equipment_id, selected_production_date
        )
        if defect_equipment_id and selected_production_date else {}
    )
    defects = db.options(
        """SELECT defect_code_id,defect_code||' · '||defect_name
           FROM defect_code WHERE is_active='Y' ORDER BY defect_code"""
    )

    if not available_dates:
        st.info("선택한 설비에 완료된 생산실적이 없습니다.")
    else:
        with st.form("defect_registration"):
            c1, c2, c3 = st.columns(3)
            with c1:
                defect_production_id = select_id(
                    "완제품 LOT*", lot_options, "defect_product_lot"
                )
            with c2:
                defect_id = select_id("불량 코드*", defects, "defect_code")
            defect_date = c3.date_input("불량 발생일*", value=date.today())
            memo = st.text_input("비고")
            if (
                st.form_submit_button("불량 등록", type="primary")
                and defect_production_id
                and defect_id
            ):
                run_action(
                    lambda: production.register_defect(
                        defect_production_id, defect_id, 1,
                        defect_date.isoformat(), memo,
                    ),
                    "완제품 LOT 불량을 등록했습니다.",
                )

    st.subheader("불량 완제품 목록")
    defective_products = quality_repository.defective_products()
    if defective_products.empty:
        st.info("등록된 불량 완제품이 없습니다.")
    else:
        show_frame(defective_products, height=380)
