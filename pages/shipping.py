from __future__ import annotations

from datetime import date

import streamlit as st

import db
from repositories import shipping as shipping_repository
from services import shipping
from ui.components import run_action, select_id, show_frame


st.title("출하 관리")
schedule_tab, pending_tab, completed_tab = st.tabs(
    ["출하 계획서", "미출하 및 출고", "출고 완료"]
)

customers = db.options(
    """SELECT partner_id,partner_code||' · '||partner_name
       FROM business_partner
       WHERE partner_type IN ('CUSTOMER','BOTH') AND is_active='Y'
       ORDER BY partner_code"""
)
products = db.options(
    """SELECT item_id,item_code||' · '||item_name
       FROM item
       WHERE item_type='PRODUCT' AND is_active='Y'
       ORDER BY item_name"""
)

with schedule_tab:
    st.subheader("출하 계획서 등록")
    with st.form("shipment_schedule"):
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            customer_id = select_id("고객사*", customers, "shipment_customer")
        with c2:
            item_id = select_id("제품*", products, "shipment_product")
        box_quantity = c3.number_input(
            "출하 수량(박스)*", min_value=1, step=1, value=1,
            help="1박스는 완제품 40개입니다.",
        )
        scheduled_date = c4.date_input(
            "출하 예정일*", value=date.today(), min_value=date.today()
        )
        if (
            st.form_submit_button("출하 계획 등록", type="primary")
            and customer_id
            and item_id
        ):
            run_action(
                lambda: shipping.create_schedule(
                    customer_id,
                    item_id,
                    scheduled_date.isoformat(),
                    int(box_quantity),
                ),
                "출하 계획서를 등록했습니다.",
            )

    st.subheader("전체 출하 계획")
    show_frame(shipping_repository.all_schedules(), height=330)

with pending_tab:
    st.subheader("미출하 계획")
    st.caption(
        "제품별 완제품 재고가 미출하 수량 이상일 때만 출고 버튼이 활성화됩니다."
    )
    pending = shipping_repository.pending_schedules()
    if pending.empty:
        st.info("현재 미출하 상태인 출하 계획이 없습니다.")
    else:
        for row in pending.to_dict("records"):
            with st.container(border=True):
                c1, c2, c3, c4, c5, c6 = st.columns([2, 2, 2, 1, 1, 1])
                c1.markdown(f"**{row['계획번호']}**\n\n{row['고객사']}")
                c2.markdown(f"**제품**\n\n{row['제품']}")
                c3.markdown(f"**출하 예정일**\n\n{row['출하예정일']}")
                c4.metric(
                    "미출하",
                    f"{int(row['미출하박스']):,}박스",
                    f"{int(row['미출하수량']):,}개",
                )
                c5.metric(
                    "출고 가능 재고",
                    f"{int(row['출고가능박스']):,}박스",
                    f"{int(row['현재재고']):,}개",
                )
                sufficient = bool(row["출고가능"])
                if c6.button(
                    "출고",
                    key=f"fulfill_schedule_{row['출하계획ID']}",
                    type="primary",
                    disabled=not sufficient,
                    width="stretch",
                ):
                    run_action(
                        lambda schedule_id=int(row["출하계획ID"]):
                            shipping.fulfill_schedule(
                                schedule_id, date.today().isoformat()
                            ),
                        "출고 처리와 완제품 재고 차감을 완료했습니다.",
                    )
                if not sufficient:
                    c6.caption("재고 부족")

with completed_tab:
    st.subheader("출고 완료 내역")
    completed = shipping_repository.completed_shipments()
    if completed.empty:
        st.info("출고 완료 내역이 없습니다.")
    else:
        show_frame(completed, height=380)
