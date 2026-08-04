from __future__ import annotations

from datetime import date

import streamlit as st

import db
from services import production
from ui.components import grid, run_action, select_id


st.title("생산 등록·품질 관리")
production_tab, material_tab, defect_tab = st.tabs(["생산 등록", "원재료 투입", "불량 등록"])

products = db.options("SELECT item_id,item_code||' · '||item_name FROM item WHERE item_type='PRODUCT' AND is_active='Y'")
equipment = db.options("SELECT equipment_id,equipment_code||' · '||equipment_name FROM equipment WHERE is_active='Y'")
productions = db.options("SELECT production_id,production_no||' · '||i.item_name FROM production p JOIN item i USING(item_id) WHERE p.status<>'CANCELED' ORDER BY production_date DESC")

with production_tab:
    with st.form("production"):
        c1, c2, c3, c4 = st.columns(4)
        request_no = c1.text_input("생산요청번호*", value=f"REQ-{date.today():%Y%m%d}-")
        item_id = select_id("제품*", products, "prod_item")
        quantity = c3.number_input("요청수량*", min_value=1, step=1, value=1000)
        equipment_id = select_id("포장 설비", equipment, "prod_eq")
        production_date = st.date_input("생산일")
        st.caption("완제품 1개당 낱개 LOT 1개와 면·스프·봉지 원재료 LOT가 각각 1개씩 투입됩니다. 40개마다 박스 1개가 생성됩니다.")
        if st.form_submit_button("생산 및 완제품 LOT 등록", type="primary") and item_id:
            run_action(
                lambda: production.create_request(
                    request_no, item_id, equipment_id, production_date.isoformat(), int(quantity)
                ),
                f"생산요청 {int(quantity):,}개와 낱개 LOT를 등록했습니다.",
            )
    grid("SELECT production_no 생산번호,item_name 제품,lot_no 완제품LOT,production_date 생산일,input_qty 투입량,p.qty 생산량,p.status 상태 FROM production p JOIN item i ON i.item_id=p.item_id JOIN lot l ON l.lot_id=p.output_lot_id ORDER BY production_date DESC")

with material_tab:
    raw_lots = db.options("SELECT lot_id,lot_no||' · '||i.item_name||' (재고 '||l.qty||')' FROM lot l JOIN item i USING(item_id) WHERE lot_type='RECEIPT' AND qty>0 ORDER BY expire_date,received_date")
    with st.form("material"):
        c1, c2, c3 = st.columns(3)
        production_id = select_id("생산번호*", productions, "mat_prod")
        lot_id = select_id("원재료 LOT*", raw_lots, "mat_lot")
        quantity = c3.number_input("사용량*", min_value=0.01)
        if st.form_submit_button("원재료 투입", type="primary") and production_id and lot_id:
            run_action(
                lambda: production.register_material(production_id, lot_id, quantity),
                "원재료 투입 및 재고 차감을 완료했습니다.",
            )
    grid("SELECT p.production_no 생산번호,i.item_name 원재료,l.lot_no LOT,pm.qty 사용량,pm.created_at 등록시각 FROM production_material pm JOIN production p USING(production_id) JOIN lot l ON l.lot_id=pm.material_lot_id JOIN item i USING(item_id) ORDER BY pm.created_at DESC")

with defect_tab:
    defects = db.options("SELECT defect_code_id,defect_code||' · '||defect_name FROM defect_code WHERE is_active='Y'")
    with st.form("defect"):
        c1, c2, c3, c4 = st.columns(4)
        production_id = select_id("생산번호*", productions, "def_prod")
        defect_id = select_id("불량 코드*", defects, "def_code")
        quantity = c3.number_input("불량 수량*", min_value=0.01)
        defect_date = c4.date_input("발생일")
        memo = st.text_input("비고")
        if st.form_submit_button("불량 등록", type="primary") and production_id and defect_id:
            run_action(
                lambda: production.register_defect(
                    production_id, defect_id, quantity, defect_date.isoformat(), memo
                ),
                "불량 실적을 등록했습니다.",
            )
    grid("SELECT p.production_no 생산번호,dc.defect_name 불량유형,pd.defect_qty 수량,pd.defect_date 발생일,pd.memo 비고 FROM production_defect pd JOIN production p USING(production_id) JOIN defect_code dc USING(defect_code_id) ORDER BY defect_date DESC")
