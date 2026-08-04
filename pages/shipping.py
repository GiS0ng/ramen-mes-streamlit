from __future__ import annotations

from datetime import date

import streamlit as st

import db
from services import shipping
from ui.components import grid, run_action, select_id


st.title("출하 관리")
schedule_tab, shipment_tab, detail_tab = st.tabs(["출하 계획", "출하 헤더", "LOT 출하"])
customers = db.options("SELECT partner_id,partner_code||' · '||partner_name FROM business_partner WHERE partner_type IN ('CUSTOMER','BOTH') AND is_active='Y'")
products = db.options("SELECT item_id,item_code||' · '||item_name FROM item WHERE item_type='PRODUCT' AND is_active='Y'")

with schedule_tab:
    with st.form("schedule"):
        c1, c2, c3, c4 = st.columns(4)
        schedule_no = c1.text_input("계획번호*", value=f"SCH-{date.today():%Y%m%d}-")
        customer_id = select_id("고객사*", customers, "sch_cust")
        item_id = select_id("제품*", products, "sch_item")
        quantity = c4.number_input("계획 수량*", min_value=0.01)
        scheduled_date = st.date_input("출하 예정일")
        if st.form_submit_button("출하계획 등록", type="primary") and customer_id and item_id:
            run_action(
                lambda: shipping.create_schedule(
                    schedule_no, customer_id, item_id, scheduled_date.isoformat(), quantity
                ),
                "출하계획을 등록했습니다.",
            )
    grid("SELECT shipment_schedule_no 계획번호,partner_name 고객,item_name 제품,scheduled_date 예정일,scheduled_qty 계획량,shipped_qty 출하량,status 상태 FROM shipment_schedule ss JOIN business_partner bp ON bp.partner_id=ss.customer_id JOIN item i USING(item_id) ORDER BY scheduled_date DESC")

with shipment_tab:
    schedules = db.options("SELECT shipment_schedule_id,shipment_schedule_no||' · '||bp.partner_name||' (잔량 '||(scheduled_qty-shipped_qty)||')' FROM shipment_schedule ss JOIN business_partner bp ON bp.partner_id=ss.customer_id WHERE ss.status IN ('PLANNED','PARTIAL_SHIPPED')")
    with st.form("shipment"):
        schedule_id = select_id("출하계획*", schedules, "ship_sch")
        c1, c2 = st.columns(2)
        shipment_no = c1.text_input("출하번호*", value=f"SHP-{date.today():%Y%m%d}-")
        shipment_date = c2.date_input("출하일")
        if st.form_submit_button("출하 헤더 생성", type="primary") and schedule_id:
            run_action(
                lambda: shipping.create_shipment(shipment_no, schedule_id, shipment_date.isoformat()),
                "출하 헤더를 생성했습니다.",
            )
    grid("SELECT shipment_no 출하번호,partner_name 고객,shipment_date 출하일,s.status 상태,shipment_schedule_no 계획번호 FROM shipment s JOIN business_partner bp ON bp.partner_id=s.customer_id LEFT JOIN shipment_schedule ss USING(shipment_schedule_id) ORDER BY shipment_date DESC")

with detail_tab:
    shipments = db.options("SELECT shipment_id,shipment_no||' · '||bp.partner_name FROM shipment s JOIN business_partner bp ON bp.partner_id=s.customer_id WHERE s.status='READY'")
    lots = db.options("SELECT lot_id,lot_no||' · '||i.item_name||' (재고 '||l.qty||')' FROM lot l JOIN item i USING(item_id) WHERE lot_type='PRODUCTION' AND qty>0")
    with st.form("ship_detail"):
        c1, c2, c3 = st.columns(3)
        shipment_id = select_id("출하번호*", shipments, "sd_ship")
        lot_id = select_id("완제품 LOT*", lots, "sd_lot")
        quantity = c3.number_input("출하 수량*", min_value=0.01)
        if st.form_submit_button("LOT 출하 및 재고 차감", type="primary") and shipment_id and lot_id:
            run_action(
                lambda: shipping.ship_lot(shipment_id, lot_id, quantity),
                "출하와 완제품 재고 차감을 완료했습니다.",
            )
    grid("SELECT s.shipment_no 출하번호,bp.partner_name 고객,l.lot_no 완제품LOT,sd.shipment_qty 출하량,s.shipment_date 출하일 FROM shipment_detail sd JOIN shipment s USING(shipment_id) JOIN business_partner bp ON bp.partner_id=s.customer_id JOIN lot l ON l.lot_id=sd.product_lot_id ORDER BY s.shipment_date DESC")
