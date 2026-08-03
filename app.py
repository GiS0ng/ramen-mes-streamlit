from __future__ import annotations

import sqlite3
from datetime import date

import pandas as pd
import streamlit as st

import db


st.set_page_config(page_title="라면 MES", page_icon="🏭", layout="wide")
database_was_missing = not db.DB_PATH.exists()
db.initialize()
if database_was_missing:
    db.seed_demo()


def run(action, success: str):
    try:
        action()
        st.success(success)
        st.rerun()
    except sqlite3.IntegrityError as exc:
        st.error(str(exc).replace("UNIQUE constraint failed:", "중복 값:"))
    except Exception as exc:
        st.error(f"처리 중 오류가 발생했습니다: {exc}")


def select(label: str, opts: dict[str, int], key: str | None = None):
    if not opts:
        st.warning(f"선택 가능한 {label} 데이터가 없습니다.")
        return None
    name = st.selectbox(label, list(opts), key=key)
    return opts[name]


def grid(sql: str, params=(), height: int = 310):
    frame = db.dataframe(sql, params)
    st.dataframe(frame, use_container_width=True, hide_index=True, height=height)
    return frame


def today():
    return date.today().isoformat()


st.markdown("""
<style>
.block-container{padding-top:1.6rem}.stMetric{background:#f7f9fc;border:1px solid #e7ebf0;
border-radius:12px;padding:12px}.subtitle{color:#607080;margin-top:-12px;margin-bottom:18px}
</style>
""", unsafe_allow_html=True)

with st.sidebar:
    st.title("🏭 라면 MES")
    st.subheader("목차")
    navigation = {
        "01. 생산현황 대시보드": "대시보드",
        "02. 기준정보 관리": "기준정보",
        "03. 구매·입고 관리": "구매·입고",
        "04. 생산 등록·품질 관리": "생산·품질",
        "05. 출하 관리": "출하",
        "06. LOT 양방향 추적": "LOT 추적",
        "07. 설비 성과": "설비",
    }
    selected_page = st.radio(
        "화면 이동",
        list(navigation),
        index=0,
        label_visibility="collapsed",
    )
    menu = navigation[selected_page]
    st.divider()
    st.caption("SQLite · LOT 기반 재고 · 트리거 자동 차감")
    st.info("공개 데모 환경입니다. 서버 재시작 또는 재배포 시 입력 데이터가 초기화될 수 있습니다.")
    if st.button("더미 데이터 생성", type="primary", use_container_width=True):
        run(db.seed_demo, "최근 30일 기준 더미 데이터를 생성했습니다.")
    if st.button("데모 데이터 초기화", use_container_width=True):
        run(db.reset_demo, "데이터베이스를 초기화했습니다.")


if menu == "대시보드":
    st.title("생산 현황 대시보드")
    st.markdown('<p class="subtitle">재고, 생산, 출하 및 품질 핵심 지표</p>', unsafe_allow_html=True)
    metrics = db.query("""SELECT
      (SELECT COUNT(*) FROM production WHERE production_date=date('now')) p,
      (SELECT COALESCE(SUM(qty),0) FROM production WHERE production_date=date('now')) q,
      (SELECT COALESCE(SUM(defect_qty),0) FROM production_defect WHERE defect_date=date('now')) d,
      (SELECT COALESCE(SUM(shipment_qty),0) FROM shipment_detail sd JOIN shipment s USING(shipment_id) WHERE s.shipment_date=date('now')) s,
      (SELECT COALESCE(SUM(qty),0) FROM lot WHERE lot_type='PRODUCTION') finished_stock,
      (SELECT COUNT(*) FROM (
          SELECT i.item_id FROM item i LEFT JOIN lot l
            ON l.item_id=i.item_id AND l.lot_type='RECEIPT'
          WHERE i.item_type='MATERIAL' AND i.is_active='Y'
          GROUP BY i.item_id HAVING COALESCE(SUM(l.qty),0)<i.safety_stock
       )) low""")[0]
    cols = st.columns(6)
    for col, label, value in zip(cols, ["오늘 생산 건", "오늘 생산량", "오늘 불량", "오늘 출하량", "현재 완제품 재고", "안전재고 경보"], metrics):
        col.metric(label, f"{value:,.0f}" if isinstance(value, (int, float)) else value)
    left, right = st.columns([3, 2])
    with left:
        st.subheader("최근 생산 수율")
        grid("""SELECT COALESCE(e.equipment_name,'미지정 설비') 설비,
        COUNT(p.production_id) 생산LOT수,ROUND(SUM(p.qty),2) 생산량,
        ROUND(SUM(COALESCE(d.defect_qty,0)),2) 불량량,
        ROUND(SUM(p.qty)-SUM(COALESCE(d.defect_qty,0)),2) 양품량,
        ROUND((SUM(p.qty)-SUM(COALESCE(d.defect_qty,0)))*100.0
              / NULLIF(SUM(p.qty),0),2) 수율
        FROM production p LEFT JOIN equipment e ON e.equipment_id=p.equipment_id
        LEFT JOIN (SELECT production_id,SUM(defect_qty) defect_qty
                   FROM production_defect GROUP BY production_id) d USING(production_id)
        WHERE p.status='COMPLETED' AND p.production_date>=date('now','-30 day')
        GROUP BY p.equipment_id,e.equipment_name ORDER BY e.equipment_name""")
        st.subheader("설비별 생산 수율")
        equipment_yield = db.dataframe("""
            SELECT COALESCE(e.equipment_name, '미지정 설비') 설비,
                   ROUND(SUM(p.qty), 2) 총생산량,
                   ROUND(SUM(COALESCE(d.defect_qty, 0)), 2) 불량량,
                   ROUND(SUM(p.qty) - SUM(COALESCE(d.defect_qty, 0)), 2) 양품량,
                   ROUND((SUM(p.qty) - SUM(COALESCE(d.defect_qty, 0))) * 100.0
                         / NULLIF(SUM(p.qty), 0), 2) 수율
            FROM production p
            LEFT JOIN equipment e ON e.equipment_id = p.equipment_id
            LEFT JOIN (
                SELECT production_id, SUM(defect_qty) defect_qty
                FROM production_defect GROUP BY production_id
            ) d ON d.production_id = p.production_id
            WHERE p.status = 'COMPLETED'
            GROUP BY p.equipment_id, e.equipment_name
            ORDER BY e.equipment_name
        """)
        if equipment_yield.empty:
            st.info("완료된 생산실적이 없어 설비별 수율을 표시할 수 없습니다.")
        else:
            chart_rows = []
            for _, row in equipment_yield.iterrows():
                for category, value in (("양품", row["양품량"]), ("불량", row["불량량"])):
                    chart_rows.append({
                        "설비": row["설비"], "구분": category, "수량": float(value),
                        "총생산량": float(row["총생산량"]), "수율": float(row["수율"]),
                    })
            yield_col, defect_col = st.columns(2)
            yield_col.markdown("**양품·불량 비율**")
            yield_col.vega_lite_chart(
                pd.DataFrame(chart_rows),
                {
                    "facet": {"field": "설비", "type": "nominal",
                              "header": {"title": None, "labelFontSize": 13}},
                    "columns": 1,
                    "spec": {
                        "mark": {"type": "arc", "innerRadius": 42, "outerRadius": 76},
                        "encoding": {
                            "theta": {"field": "수량", "type": "quantitative", "stack": True},
                            "color": {
                                "field": "구분", "type": "nominal",
                                "scale": {"domain": ["양품", "불량"],
                                          "range": ["#2E8B57", "#E45756"]},
                                "legend": {"orient": "bottom", "title": None},
                            },
                            "tooltip": [
                                {"field": "설비", "type": "nominal"},
                                {"field": "구분", "type": "nominal"},
                                {"field": "수량", "type": "quantitative", "format": ",.2f"},
                                {"field": "총생산량", "type": "quantitative", "format": ",.2f"},
                                {"field": "수율", "type": "quantitative", "format": ".2f", "title": "수율(%)"},
                            ],
                        },
                    },
                    "resolve": {"scale": {"theta": "independent"}},
                    "config": {"view": {"stroke": None}},
                },
                use_container_width=True,
            )
            defect_by_equipment = db.dataframe("""
                SELECT COALESCE(e.equipment_name,'미지정 설비') 설비,
                       dc.defect_code 불량코드,dc.defect_name 불량명,
                       COUNT(pd.production_defect_id) 발생횟수,
                       SUM(pd.defect_qty) 불량수량
                FROM production_defect pd
                JOIN production p ON p.production_id=pd.production_id
                LEFT JOIN equipment e ON e.equipment_id=p.equipment_id
                JOIN defect_code dc ON dc.defect_code_id=pd.defect_code_id
                WHERE pd.defect_date>=date('now','-30 day')
                GROUP BY p.equipment_id,e.equipment_name,dc.defect_code_id,
                         dc.defect_code,dc.defect_name
                ORDER BY e.equipment_name,발생횟수 DESC
            """)
            defect_col.markdown("**설비별 불량 코드 횟수**")
            if defect_by_equipment.empty:
                defect_col.info("최근 30일 불량 데이터가 없습니다.")
            else:
                defect_col.vega_lite_chart(
                    defect_by_equipment,
                    {
                        "facet": {"field": "설비", "type": "nominal",
                                  "header": {"title": None, "labelFontSize": 13}},
                        "columns": 1,
                        "spec": {
                            "mark": {"type": "arc", "innerRadius": 42,
                                     "outerRadius": 76},
                            "encoding": {
                                "theta": {"field": "발생횟수", "type": "quantitative",
                                          "stack": True},
                                "color": {"field": "불량명", "type": "nominal",
                                          "legend": {"orient": "bottom", "title": None}},
                                "tooltip": [
                                    {"field": "설비", "type": "nominal"},
                                    {"field": "불량코드", "type": "nominal"},
                                    {"field": "불량명", "type": "nominal"},
                                    {"field": "발생횟수", "type": "quantitative",
                                     "format": ",.0f"},
                                    {"field": "불량수량", "type": "quantitative",
                                     "format": ",.0f"},
                                ],
                            },
                        },
                        "resolve": {"scale": {"theta": "independent"}},
                        "config": {"view": {"stroke": None}},
                    },
                    use_container_width=True,
                )
    with right:
        st.subheader("원재료 재고 경보")
        frame = grid("""SELECT i.item_name 품목,COALESCE(SUM(l.qty),0) 총재고,
        i.safety_stock 안전재고,
        CASE WHEN COALESCE(SUM(l.qty),0)<i.safety_stock THEN '경고' ELSE '정상' END 상태
        FROM item i LEFT JOIN lot l ON l.item_id=i.item_id AND l.lot_type='RECEIPT'
        WHERE i.item_type='MATERIAL' AND i.is_active='Y'
        GROUP BY i.item_id,i.item_name,i.safety_stock
        ORDER BY CASE WHEN COALESCE(SUM(l.qty),0)<i.safety_stock THEN 0 ELSE 1 END,i.item_name""")
        if not frame.empty:
            chart = frame[["품목","총재고"]].rename(columns={"총재고":"재고"})
            st.vega_lite_chart(
                chart,
                {
                    "mark": {"type": "bar", "cornerRadiusTopLeft": 4,
                             "cornerRadiusTopRight": 4, "color": "#3B82F6"},
                    "encoding": {
                        "x": {
                            "field": "품목", "type": "nominal",
                            "sort": "-y",
                            "axis": {"title": None, "labelAngle": 0,
                                     "labelLimit": 110, "labelPadding": 8},
                        },
                        "y": {
                            "field": "재고", "type": "quantitative",
                            "axis": {"title": "현재 재고", "format": ",.0f"},
                        },
                        "tooltip": [
                            {"field": "품목", "type": "nominal"},
                            {"field": "재고", "type": "quantitative", "format": ",.2f"},
                        ],
                    },
                    "height": 250,
                },
                use_container_width=True,
            )

elif menu == "기준정보":
    st.title("기준정보 관리")
    tab1, tab2, tab3 = st.tabs(["품목", "거래처", "설비"])
    with tab1:
        with st.form("item"):
            c1,c2,c3,c4=st.columns(4)
            code=c1.text_input("품목 코드*"); name=c2.text_input("품목명*")
            typ=c3.selectbox("유형",["MATERIAL","PRODUCT"]); unit=c4.text_input("단위",value="EA")
            safety=st.number_input("안전재고",min_value=0.0,step=10.0)
            if st.form_submit_button("품목 등록",type="primary"):
                run(lambda: db.execute("INSERT INTO item(item_code,item_name,item_type,unit,safety_stock) VALUES(?,?,?,?,?)",(code,name,typ,unit,safety)),"품목을 등록했습니다.")
        grid("SELECT item_code 코드,item_name 품목명,item_type 유형,unit 단위,safety_stock 안전재고,is_active 사용 FROM item ORDER BY item_type,item_code")
    with tab2:
        with st.form("partner"):
            c1,c2,c3=st.columns(3); code=c1.text_input("거래처 코드*"); name=c2.text_input("거래처명*"); typ=c3.selectbox("구분",["SUPPLIER","CUSTOMER","BOTH"])
            c4,c5,c6=st.columns(3); phone=c4.text_input("전화번호"); email=c5.text_input("이메일"); address=c6.text_input("주소")
            if st.form_submit_button("거래처 등록",type="primary"):
                run(lambda: db.execute("INSERT INTO business_partner(partner_code,partner_name,partner_type,phone,email,address) VALUES(?,?,?,?,?,?)",(code,name,typ,phone,email,address)),"거래처를 등록했습니다.")
        grid("SELECT partner_code 코드,partner_name 거래처,partner_type 구분,phone 전화,email 이메일,address 주소 FROM business_partner ORDER BY partner_code")
    with tab3:
        with st.form("equipment"):
            c1,c2,c3,c4=st.columns(4); code=c1.text_input("설비 코드*"); name=c2.text_input("설비명*"); typ=c3.text_input("설비 유형"); loc=c4.text_input("설치 위치")
            if st.form_submit_button("설비 등록",type="primary"):
                run(lambda: db.execute("INSERT INTO equipment(equipment_code,equipment_name,equipment_type,location) VALUES(?,?,?,?)",(code,name,typ,loc)),"설비를 등록했습니다.")
        grid("SELECT equipment_code 코드,equipment_name 설비명,equipment_type 유형,location 위치,status 상태 FROM equipment ORDER BY equipment_code")

elif menu == "구매·입고":
    st.title("구매·입고 관리")
    tab1,tab2=st.tabs(["발주 등록","입고 처리"])
    suppliers=db.options("SELECT partner_id,partner_code||' · '||partner_name FROM business_partner WHERE partner_type IN ('SUPPLIER','BOTH') AND is_active='Y'")
    materials=db.options("SELECT item_id,item_code||' · '||item_name FROM item WHERE item_type='MATERIAL' AND is_active='Y'")
    with tab1:
        with st.form("po"):
            c1,c2,c3=st.columns(3); no=c1.text_input("발주번호*",value=f"PO-{date.today():%Y%m%d}-")
            supplier=select("공급업체*",suppliers,"po_sup"); order_date=c3.date_input("발주일")
            c4,c5,c6=st.columns(3); item=select("원재료*",materials,"po_item"); qty=c5.number_input("발주량*",min_value=0.01); price=c6.number_input("단가",min_value=0.0)
            memo=st.text_input("비고")
            if st.form_submit_button("발주 등록",type="primary") and supplier and item:
                def add_po():
                    with db.transaction() as conn:
                        cur=conn.execute("INSERT INTO purchase_order(purchase_order_no,supplier_id,order_date,memo) VALUES(?,?,?,?)",(no,supplier,order_date.isoformat(),memo))
                        conn.execute("INSERT INTO purchase_order_detail(purchase_order_id,material_item_id,order_qty,unit_price) VALUES(?,?,?,?)",(cur.lastrowid,item,qty,price))
                run(add_po,"발주를 등록했습니다.")
        grid("""SELECT po.purchase_order_no 발주번호,bp.partner_name 공급업체,i.item_name 품목,pod.order_qty 발주량,
        pod.received_qty 입고량,pod.unit_price 단가,po.status 상태,po.order_date 발주일
        FROM purchase_order po JOIN business_partner bp ON bp.partner_id=po.supplier_id JOIN purchase_order_detail pod USING(purchase_order_id)
        JOIN item i ON i.item_id=pod.material_item_id ORDER BY po.order_date DESC""")
    with tab2:
        open_details=db.options("""SELECT pod.purchase_order_detail_id,po.purchase_order_no||' · '||i.item_name||' (잔량 '||(pod.order_qty-pod.received_qty)||')'
        FROM purchase_order_detail pod JOIN purchase_order po USING(purchase_order_id) JOIN item i ON i.item_id=pod.material_item_id
        WHERE po.status<>'CANCELED' AND pod.received_qty<pod.order_qty""")
        with st.form("receipt"):
            detail=select("미입고 발주상세*",open_details,"receipt_po")
            c1,c2,c3,c4=st.columns(4); rno=c1.text_input("입고번호*",value=f"RCV-{date.today():%Y%m%d}-"); lotno=c2.text_input("입고 LOT 번호*"); rdate=c3.date_input("입고일"); qty=c4.number_input("입고량*",min_value=0.01)
            expire=st.date_input("유효기한",value=None)
            if st.form_submit_button("입고 및 LOT 생성",type="primary") and detail:
                def receive():
                    with db.transaction() as conn:
                        row=conn.execute("SELECT material_item_id,order_qty,received_qty,purchase_order_id FROM purchase_order_detail WHERE purchase_order_detail_id=?",(detail,)).fetchone()
                        if row[2]+qty>row[1]: raise ValueError("미입고 잔량을 초과할 수 없습니다.")
                        cur=conn.execute("INSERT INTO lot(lot_no,item_id,lot_type,initial_qty,qty,received_date,expire_date) VALUES(?,?,?,?,?,?,?)",(lotno,row[0],"RECEIPT",qty,qty,rdate.isoformat(),expire.isoformat() if expire else None))
                        conn.execute("INSERT INTO material_receipt(receipt_no,purchase_order_detail_id,material_lot_id,receipt_date,receipt_qty) VALUES(?,?,?,?,?)",(rno,detail,cur.lastrowid,rdate.isoformat(),qty))
                        conn.execute("UPDATE purchase_order_detail SET received_qty=received_qty+? WHERE purchase_order_detail_id=?",(qty,detail))
                        conn.execute("UPDATE purchase_order SET status=CASE WHEN NOT EXISTS(SELECT 1 FROM purchase_order_detail WHERE purchase_order_id=? AND received_qty<order_qty) THEN 'RECEIVED' ELSE 'PARTIAL_RECEIVED' END WHERE purchase_order_id=?",(row[3],row[3]))
                run(receive,"입고 처리와 LOT 생성을 완료했습니다.")
        grid("SELECT receipt_no 입고번호,lot_no LOT,item_name 품목,receipt_date 입고일,receipt_qty 입고량,expire_date 유효기한 FROM material_receipt mr JOIN lot l ON l.lot_id=mr.material_lot_id JOIN item i USING(item_id) ORDER BY receipt_date DESC")

elif menu == "생산·품질":
    st.title("생산 등록·품질 관리")
    tab1,tab2,tab3=st.tabs(["생산 등록","원재료 투입","불량 등록"])
    products=db.options("SELECT item_id,item_code||' · '||item_name FROM item WHERE item_type='PRODUCT' AND is_active='Y'")
    equipment=db.options("SELECT equipment_id,equipment_code||' · '||equipment_name FROM equipment WHERE is_active='Y'")
    productions=db.options("SELECT production_id,production_no||' · '||i.item_name FROM production p JOIN item i USING(item_id) WHERE p.status<>'CANCELED' ORDER BY production_date DESC")
    with tab1:
        with st.form("production"):
            c1,c2,c3,c4=st.columns(4); no=c1.text_input("생산요청번호*",value=f"REQ-{date.today():%Y%m%d}-"); item=select("제품*",products,"prod_item"); qty=c3.number_input("요청수량*",min_value=1,step=1,value=1000); equip=select("포장 설비",equipment,"prod_eq")
            pdate=st.date_input("생산일")
            st.caption("완제품 1개당 낱개 LOT 1개와 면·스프·봉지 원재료 LOT가 각각 1개씩 투입됩니다. 40개마다 박스 1개가 생성됩니다.")
            if st.form_submit_button("생산 및 완제품 LOT 등록",type="primary") and item:
                run(lambda: db.create_production_request(no,item,equip,pdate.isoformat(),int(qty)),f"생산요청 {int(qty):,}개와 낱개 LOT를 등록했습니다.")
        grid("SELECT production_no 생산번호,item_name 제품,lot_no 완제품LOT,production_date 생산일,input_qty 투입량,p.qty 생산량,p.status 상태 FROM production p JOIN item i ON i.item_id=p.item_id JOIN lot l ON l.lot_id=p.output_lot_id ORDER BY production_date DESC")
    with tab2:
        rawlots=db.options("SELECT lot_id,lot_no||' · '||i.item_name||' (재고 '||l.qty||')' FROM lot l JOIN item i USING(item_id) WHERE lot_type='RECEIPT' AND qty>0 ORDER BY expire_date,received_date")
        with st.form("material"):
            c1,c2,c3=st.columns(3); prod=select("생산번호*",productions,"mat_prod"); lot=select("원재료 LOT*",rawlots,"mat_lot"); qty=c3.number_input("사용량*",min_value=0.01)
            if st.form_submit_button("원재료 투입",type="primary") and prod and lot:
                run(lambda: db.execute("INSERT INTO production_material(production_id,material_lot_id,qty) VALUES(?,?,?)",(prod,lot,qty)),"원재료 투입 및 재고 차감을 완료했습니다.")
        grid("SELECT p.production_no 생산번호,i.item_name 원재료,l.lot_no LOT,pm.qty 사용량,pm.created_at 등록시각 FROM production_material pm JOIN production p USING(production_id) JOIN lot l ON l.lot_id=pm.material_lot_id JOIN item i USING(item_id) ORDER BY pm.created_at DESC")
    with tab3:
        defects=db.options("SELECT defect_code_id,defect_code||' · '||defect_name FROM defect_code WHERE is_active='Y'")
        with st.form("defect"):
            c1,c2,c3,c4=st.columns(4); prod=select("생산번호*",productions,"def_prod"); defect=select("불량 코드*",defects,"def_code"); qty=c3.number_input("불량 수량*",min_value=0.01); ddate=c4.date_input("발생일")
            memo=st.text_input("비고")
            if st.form_submit_button("불량 등록",type="primary") and prod and defect:
                run(lambda: db.execute("INSERT INTO production_defect(production_id,defect_code_id,defect_qty,defect_date,memo) VALUES(?,?,?,?,?)",(prod,defect,qty,ddate.isoformat(),memo)),"불량 실적을 등록했습니다.")
        grid("SELECT p.production_no 생산번호,dc.defect_name 불량유형,pd.defect_qty 수량,pd.defect_date 발생일,pd.memo 비고 FROM production_defect pd JOIN production p USING(production_id) JOIN defect_code dc USING(defect_code_id) ORDER BY defect_date DESC")

elif menu == "출하":
    st.title("출하 관리")
    tab1,tab2,tab3=st.tabs(["출하 계획","출하 헤더","LOT 출하"])
    customers=db.options("SELECT partner_id,partner_code||' · '||partner_name FROM business_partner WHERE partner_type IN ('CUSTOMER','BOTH') AND is_active='Y'")
    products=db.options("SELECT item_id,item_code||' · '||item_name FROM item WHERE item_type='PRODUCT' AND is_active='Y'")
    with tab1:
        with st.form("schedule"):
            c1,c2,c3,c4=st.columns(4); no=c1.text_input("계획번호*",value=f"SCH-{date.today():%Y%m%d}-"); customer=select("고객사*",customers,"sch_cust"); item=select("제품*",products,"sch_item"); qty=c4.number_input("계획 수량*",min_value=0.01)
            sdate=st.date_input("출하 예정일")
            if st.form_submit_button("출하계획 등록",type="primary") and customer and item:
                run(lambda: db.execute("INSERT INTO shipment_schedule(shipment_schedule_no,customer_id,item_id,scheduled_date,scheduled_qty) VALUES(?,?,?,?,?)",(no,customer,item,sdate.isoformat(),qty)),"출하계획을 등록했습니다.")
        grid("SELECT shipment_schedule_no 계획번호,partner_name 고객,item_name 제품,scheduled_date 예정일,scheduled_qty 계획량,shipped_qty 출하량,status 상태 FROM shipment_schedule ss JOIN business_partner bp ON bp.partner_id=ss.customer_id JOIN item i USING(item_id) ORDER BY scheduled_date DESC")
    with tab2:
        schedules=db.options("SELECT shipment_schedule_id,shipment_schedule_no||' · '||bp.partner_name||' (잔량 '||(scheduled_qty-shipped_qty)||')' FROM shipment_schedule ss JOIN business_partner bp ON bp.partner_id=ss.customer_id WHERE ss.status IN ('PLANNED','PARTIAL_SHIPPED')")
        with st.form("shipment"):
            schedule=select("출하계획*",schedules,"ship_sch"); c1,c2=st.columns(2); no=c1.text_input("출하번호*",value=f"SHP-{date.today():%Y%m%d}-"); sdate=c2.date_input("출하일")
            if st.form_submit_button("출하 헤더 생성",type="primary") and schedule:
                customer=db.query("SELECT customer_id FROM shipment_schedule WHERE shipment_schedule_id=?",(schedule,))[0][0]
                run(lambda: db.execute("INSERT INTO shipment(shipment_no,shipment_schedule_id,customer_id,shipment_date) VALUES(?,?,?,?)",(no,schedule,customer,sdate.isoformat())),"출하 헤더를 생성했습니다.")
        grid("SELECT shipment_no 출하번호,partner_name 고객,shipment_date 출하일,s.status 상태,shipment_schedule_no 계획번호 FROM shipment s JOIN business_partner bp ON bp.partner_id=s.customer_id LEFT JOIN shipment_schedule ss USING(shipment_schedule_id) ORDER BY shipment_date DESC")
    with tab3:
        ships=db.options("SELECT shipment_id,shipment_no||' · '||bp.partner_name FROM shipment s JOIN business_partner bp ON bp.partner_id=s.customer_id WHERE s.status='READY'")
        lots=db.options("SELECT lot_id,lot_no||' · '||i.item_name||' (재고 '||l.qty||')' FROM lot l JOIN item i USING(item_id) WHERE lot_type='PRODUCTION' AND qty>0")
        with st.form("ship_detail"):
            c1,c2,c3=st.columns(3); ship=select("출하번호*",ships,"sd_ship"); lot=select("완제품 LOT*",lots,"sd_lot"); qty=c3.number_input("출하 수량*",min_value=0.01)
            if st.form_submit_button("LOT 출하 및 재고 차감",type="primary") and ship and lot:
                run(lambda: db.execute("INSERT INTO shipment_detail(shipment_id,product_lot_id,shipment_qty) VALUES(?,?,?)",(ship,lot,qty)),"출하와 완제품 재고 차감을 완료했습니다.")
        grid("SELECT s.shipment_no 출하번호,bp.partner_name 고객,l.lot_no 완제품LOT,sd.shipment_qty 출하량,s.shipment_date 출하일 FROM shipment_detail sd JOIN shipment s USING(shipment_id) JOIN business_partner bp ON bp.partner_id=s.customer_id JOIN lot l ON l.lot_id=sd.product_lot_id ORDER BY s.shipment_date DESC")

elif menu == "LOT 추적":
    st.title("LOT 양방향 추적")
    direction=st.radio("추적 방향",["원재료 LOT → 완제품·고객","완제품 LOT → 원재료","박스 → 완제품 LOT","고객 → 생산번호"],horizontal=True)
    if direction.startswith("원재료"):
        opts=db.options("SELECT lot_id,lot_no||' · '||i.item_name FROM lot l JOIN item i USING(item_id) WHERE lot_type='RECEIPT'")
        chosen=select("원재료 LOT",opts,"trace_raw")
        if chosen:
            grid("""SELECT ml.lot_no 원재료LOT,mi.item_name 원재료,p.production_no 생산번호,pl.lot_no 완제품LOT,
            pi.item_name 제품,pm.qty 투입량,s.shipment_no 출하번호,bp.partner_name 고객,sd.shipment_qty 출하량
            FROM production_material pm JOIN lot ml ON ml.lot_id=pm.material_lot_id JOIN item mi ON mi.item_id=ml.item_id
            JOIN production p USING(production_id) JOIN lot pl ON pl.lot_id=p.output_lot_id JOIN item pi ON pi.item_id=p.item_id
            LEFT JOIN shipment_detail sd ON sd.product_lot_id=pl.lot_id LEFT JOIN shipment s USING(shipment_id)
            LEFT JOIN business_partner bp ON bp.partner_id=s.customer_id WHERE ml.lot_id=?""",(chosen,),420)
    elif direction.startswith("완제품"):
        opts=db.options("SELECT lot_id,lot_no||' · '||i.item_name FROM lot l JOIN item i USING(item_id) WHERE lot_type='PRODUCTION'")
        chosen=select("완제품 LOT",opts,"trace_fg")
        if chosen:
            grid("""SELECT pl.lot_no 완제품LOT,p.production_no 생산번호,mi.item_name 원재료,ml.lot_no 원재료LOT,pm.qty 사용량
            FROM production p JOIN lot pl ON pl.lot_id=p.output_lot_id JOIN production_material pm USING(production_id)
            JOIN lot ml ON ml.lot_id=pm.material_lot_id JOIN item mi ON mi.item_id=ml.item_id
            WHERE pl.lot_id=? AND mi.item_code<>'RM-BOX'""",(chosen,),420)
    elif direction.startswith("박스"):
        opts=db.options("""SELECT pb.packing_box_id,pb.box_no||' · 40개'
        FROM packing_box pb ORDER BY pb.packed_date DESC,pb.box_no""")
        chosen=select("박스번호",opts,"trace_box")
        if chosen:
            grid("""SELECT pb.box_no 박스번호,pb.box_qty 포장수량,pb.packed_date 포장일,
            l.lot_no 완제품LOT,i.item_code 제품코드,i.item_name 제품,p.production_no 생산번호,
            p.production_date 생산일,l.qty LOT현재재고
            FROM packing_box pb JOIN packing_box_detail pbd USING(packing_box_id)
            JOIN lot l ON l.lot_id=pbd.product_lot_id JOIN item i USING(item_id)
            JOIN production p ON p.output_lot_id=l.lot_id
            WHERE pb.packing_box_id=? ORDER BY l.lot_no""",(chosen,),420)
            st.caption("박스 1개에는 완제품 낱개 LOT 40개가 들어갑니다.")
    else:
        opts=db.options("SELECT partner_id,partner_code||' · '||partner_name FROM business_partner WHERE partner_type IN ('CUSTOMER','BOTH')")
        chosen=select("고객사",opts,"trace_customer")
        if chosen: grid("SELECT customer_name 고객,shipment_no 출하번호,shipment_date 출하일,production_no 생산번호,product_lot_no 완제품LOT,item_name 제품,shipment_qty 출하량,unit 단위 FROM v_shipment_production_trace WHERE partner_id=? ORDER BY shipment_date DESC",(chosen,),420)

else:
    st.title("설비 성과")
    tab1,tab2=st.tabs(["가동 실적 등록","성과 조회"])
    equipment=db.options("SELECT equipment_id,equipment_code||' · '||equipment_name FROM equipment WHERE is_active='Y'")
    productions=db.options("SELECT production_id,production_no FROM production ORDER BY production_date DESC")
    with tab1:
        with st.form("operation"):
            c1,c2,c3=st.columns(3); equip=select("설비*",equipment,"op_eq"); prod=select("생산번호",productions,"op_prod"); odate=c3.date_input("가동일")
            c4,c5,c6=st.columns(3); planned=c4.number_input("계획 시간(분)",min_value=0,step=10); running=c5.number_input("가동 시간(분)",min_value=0,step=10); down=c6.number_input("비가동 시간(분)",min_value=0,step=10)
            reason=st.text_input("비가동 사유")
            if st.form_submit_button("가동 실적 등록",type="primary") and equip:
                run(lambda: db.execute("INSERT INTO equipment_operation(equipment_id,production_id,operation_date,planned_minutes,running_minutes,downtime_minutes,downtime_reason) VALUES(?,?,?,?,?,?,?)",(equip,prod,odate.isoformat(),planned,running,down,reason)),"설비 가동 실적을 등록했습니다.")
    with tab2:
        grid("""SELECT e.equipment_code 설비코드,e.equipment_name 설비명,COALESCE(SUM(eo.planned_minutes),0) 계획시간,
        COALESCE(SUM(eo.running_minutes),0) 가동시간,COALESCE(SUM(eo.downtime_minutes),0) 비가동시간,
        ROUND(SUM(eo.running_minutes)*100.0/NULLIF(SUM(eo.planned_minutes),0),2) 가동률
        FROM equipment e LEFT JOIN equipment_operation eo USING(equipment_id) GROUP BY e.equipment_id ORDER BY e.equipment_code""")
