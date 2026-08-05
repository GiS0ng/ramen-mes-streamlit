from __future__ import annotations

from datetime import date, timedelta

import streamlit as st

import db
from services import purchasing
from ui.components import grid, run_action, select_id


st.title("구매·입고 관리")
order_tab, receipt_tab = st.tabs(["발주서", "발주 현황 및 입고 처리"])

suppliers = db.options(
    """SELECT partner_id,partner_code||' · '||partner_name
       FROM business_partner
       WHERE partner_type IN ('SUPPLIER','BOTH') AND is_active='Y'
       ORDER BY partner_code"""
)
materials = db.options(
    """SELECT item_id,item_code||' · '||item_name
       FROM item
       WHERE item_type='MATERIAL' AND is_active='Y'
       ORDER BY item_name"""
)

with order_tab:
    st.subheader("원재료 발주서 작성")
    st.caption("발주번호와 발주일은 등록 시 자동으로 생성됩니다.")
    with st.form("purchase_order_form"):
        c1, c2 = st.columns(2)
        with c1:
            supplier_id = select_id("공급업체*", suppliers, "po_supplier")
        with c2:
            item_id = select_id("원재료*", materials, "po_material")
        c3, c4 = st.columns(2)
        quantity = c3.number_input("발주량*", min_value=1, step=1, value=100)
        expected_date = c4.date_input(
            "입고 희망일*",
            value=date.today() + timedelta(days=7),
            min_value=date.today(),
        )
        submitted = st.form_submit_button("발주서 등록", type="primary")
        if submitted and supplier_id and item_id:
            run_action(
                lambda: purchasing.create_purchase_order(
                    supplier_id, item_id, int(quantity), expected_date
                ),
                "발주서를 등록했습니다.",
            )

    st.subheader("최근 발주서")
    grid(
        """SELECT po.purchase_order_no 발주번호,bp.partner_name 공급업체,
                  i.item_name 원재료,pod.order_qty 발주량,
                  po.order_date 발주일,po.expected_date 입고희망일,
                  CASE WHEN pod.received_qty>=pod.order_qty THEN '입고 완료'
                       ELSE '미입고' END 입고상태
           FROM purchase_order po
           JOIN business_partner bp ON bp.partner_id=po.supplier_id
           JOIN purchase_order_detail pod USING(purchase_order_id)
           JOIN item i ON i.item_id=pod.material_item_id
           ORDER BY po.order_date DESC,po.purchase_order_id DESC"""
    )

with receipt_tab:
    st.subheader("미입고 발주서")
    open_orders = grid(
        """SELECT po.purchase_order_no 발주번호,bp.partner_name 공급업체,
                  i.item_name 원재료,pod.order_qty 발주량,
                  pod.received_qty 기입고량,
                  pod.order_qty-pod.received_qty 미입고량,
                  po.order_date 발주일,po.expected_date 입고희망일,
                  '미입고' 입고상태
           FROM purchase_order_detail pod
           JOIN purchase_order po USING(purchase_order_id)
           JOIN business_partner bp ON bp.partner_id=po.supplier_id
           JOIN item i ON i.item_id=pod.material_item_id
           WHERE po.status<>'CANCELED' AND pod.received_qty<pod.order_qty
           ORDER BY po.expected_date,po.purchase_order_id""",
        height=260,
    )

    if open_orders.empty:
        st.info("현재 입고 대기 중인 발주서가 없습니다.")
    else:
        open_details = db.options(
            """SELECT pod.purchase_order_detail_id,
                      po.purchase_order_no||' · '||i.item_name||
                      ' · 미입고 '||(pod.order_qty-pod.received_qty)||' EA'
               FROM purchase_order_detail pod
               JOIN purchase_order po USING(purchase_order_id)
               JOIN item i ON i.item_id=pod.material_item_id
               WHERE po.status<>'CANCELED' AND pod.received_qty<pod.order_qty
               ORDER BY po.expected_date,po.purchase_order_id"""
        )
        with st.form("field_receipt_form"):
            detail_id = select_id("입고 처리할 발주서*", open_details, "receipt_order")
            receipt_date = st.date_input("실제 입고일*", value=date.today())
            st.caption(
                "현장에서 수량과 품목을 확인한 후 처리하세요. "
                "미입고 잔량 전체가 입고되며 원재료 1개마다 LOT 1개가 자동 생성됩니다."
            )
            confirmed = st.checkbox("현장에서 품목과 수량을 확인했습니다.")
            submitted = st.form_submit_button("입고 처리", type="primary")
            if submitted:
                if not confirmed:
                    st.error("현장에서 품목과 수량을 확인한 후 체크해 주세요.")
                elif detail_id:
                    run_action(
                        lambda: purchasing.receive_purchase_order(detail_id, receipt_date),
                        "현장 확인 발주서의 입고 처리를 완료했습니다.",
                    )

    st.subheader("입고 완료 발주서")
    grid(
        """SELECT po.purchase_order_no 발주번호,bp.partner_name 공급업체,
                  i.item_name 원재료,pod.order_qty 발주량,
                  SUM(mr.receipt_qty) 입고량,MAX(mr.receipt_date) 입고일,
                  po.expected_date 입고희망일,'입고 완료' 입고상태
           FROM purchase_order_detail pod
           JOIN purchase_order po USING(purchase_order_id)
           JOIN business_partner bp ON bp.partner_id=po.supplier_id
           JOIN item i ON i.item_id=pod.material_item_id
           JOIN material_receipt mr USING(purchase_order_detail_id)
           WHERE pod.received_qty>=pod.order_qty
           GROUP BY pod.purchase_order_detail_id
           ORDER BY MAX(mr.receipt_date) DESC,po.purchase_order_id DESC""",
        height=300,
    )
