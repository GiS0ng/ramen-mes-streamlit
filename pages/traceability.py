from __future__ import annotations

from datetime import date, timedelta

import streamlit as st

import db
from repositories import traceability
from ui.components import grid, select_id, show_frame


st.title("LOT 양방향 추적")
direction = st.radio(
    "추적 방향",
    [
        "원재료 LOT → 완제품",
        "원재료 LOT → 고객 납품",
        "완제품 LOT → 원재료",
        "박스 → 완제품 LOT",
        "고객 → 생산번호",
    ],
    horizontal=True,
)

if direction == "원재료 LOT → 완제품":
    st.markdown("**원재료 조회 조건**")
    material_column, receipt_start_column, receipt_end_column = st.columns(3)
    materials = {"전체 원재료": None, **traceability.material_options()}
    material_label = material_column.selectbox(
        "원재료명",
        list(materials),
        key="raw_product_material",
    )
    material_item_id = materials[material_label]
    receipt_start_date = receipt_start_column.date_input(
        "원재료 입고일 시작",
        value=date.today() - timedelta(days=30),
        key="raw_receipt_start",
    )
    receipt_end_date = receipt_end_column.date_input(
        "원재료 입고일 종료",
        value=date.today(),
        key="raw_receipt_end",
    )
    if receipt_start_date > receipt_end_date:
        st.warning("원재료 입고일 시작은 종료일보다 늦을 수 없습니다.")
        options = {}
    else:
        options = traceability.raw_material_options(
            material_item_id,
            receipt_start_date.isoformat(),
            receipt_end_date.isoformat(),
        )
    chosen = select_id("원재료 LOT", options, "trace_raw")
    st.markdown("**완제품 생산일 조회 조건**")
    start_column, end_column = st.columns(2)
    start_date = start_column.date_input(
        "생산일 시작",
        value=date.today() - timedelta(days=30),
        key="raw_product_start",
    )
    end_date = end_column.date_input("생산일 종료", value=date.today(), key="raw_product_end")
    if chosen:
        if start_date > end_date:
            st.warning("생산일 시작은 종료일보다 늦을 수 없습니다.")
        else:
            frame = traceability.raw_material_to_products(
                chosen, start_date.isoformat(), end_date.isoformat()
            )
            if frame.empty:
                st.info("선택한 기간에 해당 원재료로 생산된 완제품이 없습니다.")
            else:
                show_frame(frame, 420)
elif direction == "원재료 LOT → 고객 납품":
    options = traceability.raw_material_options()
    chosen = select_id("원재료 LOT", options, "trace_raw_customer")
    customers = {"전체 고객사": None, **traceability.customer_options()}
    customer_label = st.selectbox("고객사", list(customers), key="raw_customer")
    customer_id = customers[customer_label]
    start_column, end_column = st.columns(2)
    start_date = start_column.date_input(
        "출하일 시작",
        value=date.today() - timedelta(days=30),
        key="raw_shipment_start",
    )
    end_date = end_column.date_input("출하일 종료", value=date.today(), key="raw_shipment_end")
    if chosen:
        if start_date > end_date:
            st.warning("출하일 시작은 종료일보다 늦을 수 없습니다.")
        else:
            frame = traceability.raw_material_to_shipments(
                chosen,
                start_date.isoformat(),
                end_date.isoformat(),
                customer_id,
            )
            if frame.empty:
                st.info("선택한 고객사와 출하일 조건에 해당하는 납품 이력이 없습니다.")
            else:
                show_frame(frame, 420)
elif direction.startswith("완제품"):
    options = db.options("SELECT lot_id,lot_no||' · '||i.item_name FROM lot l JOIN item i USING(item_id) WHERE lot_type='PRODUCTION'")
    chosen = select_id("완제품 LOT", options, "trace_fg")
    if chosen:
        grid("""SELECT pl.lot_no 완제품LOT,p.production_no 생산번호,mi.item_name 원재료,ml.lot_no 원재료LOT,pm.qty 사용량
        FROM production p JOIN lot pl ON pl.lot_id=p.output_lot_id JOIN production_material pm USING(production_id)
        JOIN lot ml ON ml.lot_id=pm.material_lot_id JOIN item mi ON mi.item_id=ml.item_id
        WHERE pl.lot_id=? AND mi.item_code<>'RM-BOX'""", (chosen,), 420)
elif direction.startswith("박스"):
    options = db.options("SELECT pb.packing_box_id,pb.box_no||' · 40개' FROM packing_box pb ORDER BY pb.packed_date DESC,pb.box_no")
    chosen = select_id("박스번호", options, "trace_box")
    if chosen:
        grid("""SELECT pb.box_no 박스번호,pb.box_qty 포장수량,pb.packed_date 포장일,
        l.lot_no 완제품LOT,i.item_code 제품코드,i.item_name 제품,p.production_no 생산번호,
        p.production_date 생산일,l.qty LOT현재재고
        FROM packing_box pb JOIN packing_box_detail pbd USING(packing_box_id)
        JOIN lot l ON l.lot_id=pbd.product_lot_id JOIN item i USING(item_id)
        JOIN production p ON p.output_lot_id=l.lot_id
        WHERE pb.packing_box_id=? ORDER BY l.lot_no""", (chosen,), 420)
        st.caption("박스 1개에는 완제품 낱개 LOT 40개가 들어갑니다.")
else:
    options = db.options("SELECT partner_id,partner_code||' · '||partner_name FROM business_partner WHERE partner_type IN ('CUSTOMER','BOTH')")
    chosen = select_id("고객사", options, "trace_customer")
    if chosen:
        grid("SELECT customer_name 고객,shipment_no 출하번호,shipment_date 출하일,production_no 생산번호,product_lot_no 완제품LOT,item_name 제품,shipment_qty 출하량,unit 단위 FROM v_shipment_production_trace WHERE partner_id=? ORDER BY shipment_date DESC", (chosen,), 420)
