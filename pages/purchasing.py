from __future__ import annotations

from datetime import date

import streamlit as st

import db
from services import purchasing
from ui.components import grid, run_action, select_id


st.title("구매·입고 관리")
order_tab, receipt_tab = st.tabs(["발주 등록", "입고 처리"])
suppliers = db.options("SELECT partner_id,partner_code||' · '||partner_name FROM business_partner WHERE partner_type IN ('SUPPLIER','BOTH') AND is_active='Y'")
materials = db.options("SELECT item_id,item_code||' · '||item_name FROM item WHERE item_type='MATERIAL' AND is_active='Y'")

with order_tab:
    with st.form("po"):
        c1, c2, c3 = st.columns(3)
        order_no = c1.text_input("발주번호*", value=f"PO-{date.today():%Y%m%d}-")
        supplier_id = select_id("공급업체*", suppliers, "po_sup")
        order_date = c3.date_input("발주일")
        c4, c5, c6 = st.columns(3)
        item_id = select_id("원재료*", materials, "po_item")
        quantity = c5.number_input("발주량*", min_value=0.01)
        unit_price = c6.number_input("단가", min_value=0.0)
        memo = st.text_input("비고")
        if st.form_submit_button("발주 등록", type="primary") and supplier_id and item_id:
            run_action(
                lambda: purchasing.create_purchase_order(
                    order_no, supplier_id, order_date, item_id, quantity, unit_price, memo
                ),
                "발주를 등록했습니다.",
            )
    grid("""SELECT po.purchase_order_no 발주번호,bp.partner_name 공급업체,i.item_name 품목,pod.order_qty 발주량,
    pod.received_qty 입고량,pod.unit_price 단가,po.status 상태,po.order_date 발주일
    FROM purchase_order po JOIN business_partner bp ON bp.partner_id=po.supplier_id JOIN purchase_order_detail pod USING(purchase_order_id)
    JOIN item i ON i.item_id=pod.material_item_id ORDER BY po.order_date DESC""")

with receipt_tab:
    open_details = db.options("""SELECT pod.purchase_order_detail_id,po.purchase_order_no||' · '||i.item_name||' (잔량 '||(pod.order_qty-pod.received_qty)||')'
    FROM purchase_order_detail pod JOIN purchase_order po USING(purchase_order_id) JOIN item i ON i.item_id=pod.material_item_id
    WHERE po.status<>'CANCELED' AND pod.received_qty<pod.order_qty""")
    with st.form("receipt"):
        detail_id = select_id("미입고 발주상세*", open_details, "receipt_po")
        c1, c2, c3, c4 = st.columns(4)
        receipt_no = c1.text_input("입고번호*", value=f"RCV-{date.today():%Y%m%d}-")
        lot_no = c2.text_input("입고 LOT 번호*")
        receipt_date = c3.date_input("입고일")
        quantity = c4.number_input("입고량*", min_value=0.01)
        expire_date = st.date_input("유효기한", value=None)
        if st.form_submit_button("입고 및 LOT 생성", type="primary") and detail_id:
            run_action(
                lambda: purchasing.receive_material(
                    detail_id, receipt_no, lot_no, receipt_date, quantity, expire_date
                ),
                "입고 처리와 LOT 생성을 완료했습니다.",
            )
    grid("SELECT receipt_no 입고번호,lot_no LOT,item_name 품목,receipt_date 입고일,receipt_qty 입고량,expire_date 유효기한 FROM material_receipt mr JOIN lot l ON l.lot_id=mr.material_lot_id JOIN item i USING(item_id) ORDER BY receipt_date DESC")
