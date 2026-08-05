from __future__ import annotations

import streamlit as st

from domain.rules import PACKAGING_CAPACITY_PER_MINUTE
from services import master_data
from ui.components import grid, run_action


st.title("기준정보 관리")
item_tab, partner_tab, equipment_tab = st.tabs(["품목", "거래처", "설비"])

with item_tab:
    with st.form("item"):
        c1, c2, c3, c4 = st.columns(4)
        code = c1.text_input("품목 코드*")
        name = c2.text_input("품목명*")
        item_type = c3.selectbox("유형", ["MATERIAL", "PRODUCT"])
        unit = c4.text_input("단위", value="EA")
        safety_stock = st.number_input("안전재고", min_value=0.0, step=10.0)
        if st.form_submit_button("품목 등록", type="primary"):
            run_action(
                lambda: master_data.create_item(code, name, item_type, unit, safety_stock),
                "품목을 등록했습니다.",
            )
    grid("SELECT item_code 코드,item_name 품목명,item_type 유형,unit 단위,safety_stock 안전재고,is_active 사용 FROM item ORDER BY item_type,item_code")

with partner_tab:
    with st.form("partner"):
        c1, c2, c3 = st.columns(3)
        code = c1.text_input("거래처 코드*")
        name = c2.text_input("거래처명*")
        partner_type = c3.selectbox("구분", ["SUPPLIER", "CUSTOMER", "BOTH"])
        c4, c5, c6 = st.columns(3)
        phone = c4.text_input("전화번호")
        email = c5.text_input("이메일")
        address = c6.text_input("주소")
        if st.form_submit_button("거래처 등록", type="primary"):
            run_action(
                lambda: master_data.create_partner(code, name, partner_type, phone, email, address),
                "거래처를 등록했습니다.",
            )
    grid("SELECT partner_code 코드,partner_name 거래처,partner_type 구분,phone 전화,email 이메일,address 주소 FROM business_partner ORDER BY partner_code")

with equipment_tab:
    with st.form("equipment"):
        c1, c2, c3, c4, c5 = st.columns(5)
        code_number = c1.number_input(
            "설비 코드 번호*",
            min_value=1,
            step=1,
            value=3,
            help="숫자만 입력하면 EQ-PACK- 접두사가 자동으로 붙습니다.",
        )
        code = f"EQ-PACK-{int(code_number):02d}"
        c1.caption(f"생성 코드: {code}")
        name = c2.text_input("설비명*")
        equipment_type = c3.text_input("설비 유형")
        location = c4.text_input("설치 위치")
        capacity_per_minute = c5.number_input(
            "분당 생산능력*",
            min_value=0.01,
            value=float(PACKAGING_CAPACITY_PER_MINUTE),
            step=0.1,
        )
        if st.form_submit_button("설비 등록", type="primary"):
            run_action(
                lambda: master_data.create_equipment(
                    code, name, equipment_type, location, capacity_per_minute
                ),
                "설비를 등록했습니다.",
            )
    grid("SELECT equipment_code 코드,equipment_name 설비명,equipment_type 유형,location 위치,capacity_per_minute 분당생산능력,status 상태 FROM equipment ORDER BY equipment_code")
