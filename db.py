from __future__ import annotations

import sqlite3
import random
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Iterable, Sequence

import pandas as pd


ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
DB_PATH = DATA_DIR / "mes.db"
SCHEMA_PATH = ROOT / "schema.sql"


def connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def transaction():
    conn = connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def initialize() -> None:
    with connect() as conn:
        conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        conn.commit()
    seed_masters()


def execute(sql: str, params: Sequence = ()) -> int:
    with transaction() as conn:
        cur = conn.execute(sql, params)
        return int(cur.lastrowid)


def query(sql: str, params: Sequence = ()) -> list[sqlite3.Row]:
    with connect() as conn:
        return conn.execute(sql, params).fetchall()


def dataframe(sql: str, params: Sequence = ()) -> pd.DataFrame:
    with connect() as conn:
        return pd.read_sql_query(sql, conn, params=params)


def options(sql: str, params: Sequence = ()) -> dict[str, int]:
    return {str(row[1]): int(row[0]) for row in query(sql, params)}


def seed_masters() -> None:
    with transaction() as conn:
        conn.executemany(
            "INSERT OR IGNORE INTO item(item_code,item_name,item_type,unit,safety_stock) VALUES(?,?,?,?,?)",
            [
                ("RM-NOODLE", "라면 면", "MATERIAL", "EA", 500),
                ("RM-SOUP", "분말 스프", "MATERIAL", "EA", 500),
                ("RM-PACK", "포장지", "MATERIAL", "EA", 500),
                ("FG-RAMEN", "봉지 라면", "PRODUCT", "EA", 500),
            ],
        )
        conn.executemany(
            "INSERT OR IGNORE INTO business_partner(partner_code,partner_name,partner_type) VALUES(?,?,?)",
            [("SUP-001", "대한식품원료", "SUPPLIER"), ("CUS-001", "행복마트", "CUSTOMER")],
        )
        conn.execute(
            "INSERT OR IGNORE INTO equipment(equipment_code,equipment_name,equipment_type,location) VALUES(?,?,?,?)",
            ("EQ-PACK-01", "라면 포장 1호기", "포장설비", "1공장"),
        )
        conn.executemany(
            "INSERT OR IGNORE INTO defect_code(defect_code,defect_name,description) VALUES(?,?,?)",
            [
                ("DEF-PACK", "포장 불량", "포장지 파손, 밀봉 또는 인쇄 불량"),
                ("DEF-NOODLE-MISSING", "면 누락", "완제품 내부 면 블록 누락"),
                ("DEF-SOUP-MISSING", "스프 누락", "완제품 내부 스프 누락"),
            ],
        )


def reset_demo() -> None:
    initialize()
    # Windows에서는 다른 라이브러리가 SQLite 파일 핸들을 잠시 유지할 수 있으므로
    # 파일 삭제 대신 한 트랜잭션 안에서 업무 데이터를 안전하게 비운다.
    tables = [
        "equipment_operation", "production_defect", "defect_code",
        "shipment_detail", "shipment", "shipment_schedule", "packing_box_detail", "packing_box",
        "product_box", "production_request_unit", "production_request", "material_receipt",
        "purchase_order_detail", "purchase_order", "production_material",
        "production", "lot", "equipment", "business_partner", "item",
    ]
    conn = connect()
    try:
        conn.execute("PRAGMA foreign_keys = OFF")
        for table in tables:
            conn.execute(f"DELETE FROM {table}")
        conn.commit()
    finally:
        conn.close()
    seed_masters()


def seed_demo(days: int = 30, seed: int = 20260803) -> None:
    """재현 가능한 MES 데모 업무 데이터를 전체 프로세스 순서로 생성한다."""
    reset_demo()
    rng = random.Random(seed)
    end = date.today()
    start = end - timedelta(days=days - 1)

    with transaction() as conn:
        # 시연에 충분한 마스터 확장
        conn.executemany(
            "INSERT OR IGNORE INTO item(item_code,item_name,item_type,unit,safety_stock) VALUES(?,?,?,?,?)",
            [
                ("RM-BOX", "포장 박스", "MATERIAL", "EA", 300),
                ("FG-SPICY", "매운맛 라면", "PRODUCT", "EA", 500),
                ("FG-MILD", "순한맛 라면", "PRODUCT", "EA", 500),
            ],
        )
        conn.executemany(
            "INSERT OR IGNORE INTO business_partner(partner_code,partner_name,partner_type,phone,address) VALUES(?,?,?,?,?)",
            [
                ("SUP-002", "한빛포장", "SUPPLIER", "02-555-0102", "경기도 화성시"),
                ("CUS-002", "우리유통", "CUSTOMER", "02-555-0202", "서울시 송파구"),
                ("CUS-003", "대성편의점", "CUSTOMER", "02-555-0203", "서울시 강남구"),
            ],
        )
        conn.executemany(
            "INSERT OR IGNORE INTO equipment(equipment_code,equipment_name,equipment_type,location) VALUES(?,?,?,?)",
            [
                ("EQ-LINE-02", "라면 생산 2호 라인", "생산라인", "1공장"),
                ("EQ-PACK-01", "자동 포장기", "포장설비", "1공장"),
            ],
        )

        materials = conn.execute("SELECT item_id,item_code FROM item WHERE item_type='MATERIAL'").fetchall()
        products = conn.execute("SELECT item_id,item_code FROM item WHERE item_type='PRODUCT'").fetchall()
        suppliers = [r[0] for r in conn.execute("SELECT partner_id FROM business_partner WHERE partner_type IN ('SUPPLIER','BOTH')")]
        customers = [r[0] for r in conn.execute("SELECT partner_id FROM business_partner WHERE partner_type IN ('CUSTOMER','BOTH')")]
        equipment = [r[0] for r in conn.execute("SELECT equipment_id FROM equipment WHERE equipment_type='생산라인'")]
        defects = [r[0] for r in conn.execute("SELECT defect_code_id FROM defect_code")]

        # 재료별 2회 발주/입고: 트리거 투입용 충분한 FEFO 재고 확보
        receipt_lots: dict[str, list[int]] = {r[1]: [] for r in materials}
        for mi, (item_id, item_code) in enumerate(materials, 1):
            for batch in range(2):
                d = start + timedelta(days=batch * 14 + mi % 4)
                qty = 8000.0
                po_no = f"PO-D-{mi:02d}-{batch+1:02d}"
                po = conn.execute(
                    "INSERT INTO purchase_order(purchase_order_no,supplier_id,order_date,expected_date,status,memo) VALUES(?,?,?,?,?,?)",
                    (po_no, suppliers[(mi + batch) % len(suppliers)], d.isoformat(), (d + timedelta(days=2)).isoformat(), "RECEIVED", "데모 자동 발주"),
                ).lastrowid
                detail = conn.execute(
                    "INSERT INTO purchase_order_detail(purchase_order_id,material_item_id,order_qty,received_qty,unit_price) VALUES(?,?,?,?,?)",
                    (po, item_id, qty, qty, rng.randint(80, 900)),
                ).lastrowid
                receipt_date = d + timedelta(days=2)
                lot_no = f"RM-{item_code[3:]}-{receipt_date:%Y%m%d}-{batch+1:02d}"
                lot = conn.execute(
                    "INSERT INTO lot(lot_no,item_id,lot_type,initial_qty,qty,received_date,expire_date) VALUES(?,?,?,?,?,?,?)",
                    (lot_no, item_id, "RECEIPT", qty, qty, receipt_date.isoformat(), (receipt_date + timedelta(days=180)).isoformat()),
                ).lastrowid
                conn.execute(
                    "INSERT INTO material_receipt(receipt_no,purchase_order_detail_id,material_lot_id,receipt_date,receipt_qty) VALUES(?,?,?,?,?)",
                    (f"RCV-D-{mi:02d}-{batch+1:02d}", detail, lot, receipt_date.isoformat(), qty),
                )
                receipt_lots[item_code].append(lot)

        production_rows: list[tuple[int, int, int, str]] = []
        # 최근 30일 동안 영업일 중심 18건 생산
        sequence = 1
        for offset in range(days):
            production_date = start + timedelta(days=offset)
            if production_date.weekday() >= 5 or offset % 3 == 2:
                continue
            product_id, product_code = products[sequence % len(products)]
            output_qty = float(rng.randrange(720, 1101, 10))
            production_no = f"PRD-D-{production_date:%Y%m%d}-{sequence:03d}"
            product_lot_no = f"FG-{product_code[3:]}-{production_date:%Y%m%d}-{sequence:03d}"
            product_lot = conn.execute(
                "INSERT INTO lot(lot_no,item_id,lot_type,initial_qty,qty,produced_date,expire_date) VALUES(?,?,?,?,?,?,?)",
                (product_lot_no, product_id, "PRODUCTION", output_qty, output_qty, production_date.isoformat(), (production_date + timedelta(days=150)).isoformat()),
            ).lastrowid
            production = conn.execute(
                """INSERT INTO production(production_no,item_id,output_lot_id,equipment_id,production_date,qty,
                planned_start_time,planned_end_time,actual_start_time,actual_end_time,status)
                VALUES(?,?,?,?,?,?,?,?,?,?, 'COMPLETED')""",
                (production_no, product_id, product_lot, equipment[sequence % len(equipment)], production_date.isoformat(), output_qty,
                 f"{production_date} 08:00:00", f"{production_date} 17:00:00", f"{production_date} 08:{rng.randint(0,12):02d}:00", f"{production_date} 16:{rng.randint(35,59):02d}:00"),
            ).lastrowid

            # 라면 1개 기준 주요 자재 투입량. 생산 투입 트리거가 재고 차감.
            # 포장 박스는 완제품 40개당 1박스를 사용한다.
            usage = {"RM-NOODLE": output_qty, "RM-SOUP": output_qty, "RM-PACK": output_qty, "RM-BOX": output_qty / 40}
            for item_code, used_qty in usage.items():
                if item_code not in receipt_lots:
                    continue
                candidates = receipt_lots[item_code]
                chosen = next((lot_id for lot_id in candidates if conn.execute("SELECT qty FROM lot WHERE lot_id=?", (lot_id,)).fetchone()[0] >= used_qty), candidates[-1])
                conn.execute("INSERT INTO production_material(production_id,material_lot_id,qty) VALUES(?,?,?)", (production, chosen, round(used_qty, 3)))

            defect_qty = float(rng.randint(3, 22))
            conn.execute(
                "INSERT INTO production_defect(production_id,defect_code_id,defect_qty,defect_date,memo) VALUES(?,?,?,?,?)",
                (production, defects[sequence % len(defects)], defect_qty, production_date.isoformat(), "공정 샘플 불량"),
            )
            planned = 540
            downtime = rng.randint(18, 65)
            conn.execute(
                "INSERT INTO equipment_operation(equipment_id,production_id,operation_date,planned_minutes,running_minutes,downtime_minutes,downtime_reason) VALUES(?,?,?,?,?,?,?)",
                (equipment[sequence % len(equipment)], production, production_date.isoformat(), planned, planned - downtime, downtime, rng.choice(["품목 교체", "세척", "예방 점검", "원료 대기"])),
            )
            production_rows.append((production, product_lot, product_id, production_date.isoformat()))

            # 개별 박스는 동일 완제품 LOT 40개로 구성한다. 40개 미만 잔량은 미포장으로 남긴다.
            full_box_count = int(output_qty // 40)
            conn.executemany(
                "INSERT INTO product_box(box_no,product_lot_id,box_qty,packed_date) VALUES(?,?,40,?)",
                [
                    (f"BOX-{production_date:%Y%m%d}-{sequence:03d}-{box_seq:04d}", product_lot, production_date.isoformat())
                    for box_seq in range(1, full_box_count + 1)
                ],
            )
            sequence += 1

        # 생산 LOT 중 70%를 고객에게 출하, 계획 누계는 트리거로 갱신
        for idx, (_, product_lot, product_id, produced) in enumerate(production_rows[:-2], 1):
            shipment_date = min(end, date.fromisoformat(produced) + timedelta(days=rng.randint(1, 4)))
            current_qty = conn.execute("SELECT qty FROM lot WHERE lot_id=?", (product_lot,)).fetchone()[0]
            ship_qty = float(max(10, int(current_qty * rng.uniform(0.55, 0.82) // 10 * 10)))
            schedule = conn.execute(
                "INSERT INTO shipment_schedule(shipment_schedule_no,customer_id,item_id,scheduled_date,scheduled_qty) VALUES(?,?,?,?,?)",
                (f"SCH-D-{idx:03d}", customers[idx % len(customers)], product_id, shipment_date.isoformat(), ship_qty),
            ).lastrowid
            shipment = conn.execute(
                "INSERT INTO shipment(shipment_no,shipment_schedule_id,customer_id,shipment_date,status,memo) VALUES(?,?,?,?,?,?)",
                (f"SHP-D-{idx:03d}", schedule, customers[idx % len(customers)], shipment_date.isoformat(), "SHIPPED", "데모 자동 출하"),
            ).lastrowid
            conn.execute("INSERT INTO shipment_detail(shipment_id,product_lot_id,shipment_qty) VALUES(?,?,?)", (shipment, product_lot, ship_qty))


# 낱개 직렬 LOT 데모 규칙. 아래 재정의가 기존 묶음 LOT 생성기를 대체한다.
def seed_demo(days: int = 30, seed: int = 20260803) -> None:
    """생산요청별 낱개 완제품/원재료 LOT와 40개입 박스를 생성한다."""
    reset_demo()
    rng = random.Random(seed)
    base_date = date.today() - timedelta(days=4)

    with transaction() as conn:
        conn.executemany(
            "INSERT OR IGNORE INTO item(item_code,item_name,item_type,unit,safety_stock) VALUES(?,?,?,?,?)",
            [
                ("FG-SPICY", "매운맛 라면", "PRODUCT", "EA", 500),
                ("FG-MILD", "순한맛 라면", "PRODUCT", "EA", 500),
            ],
        )
        conn.executemany(
            "INSERT OR IGNORE INTO business_partner(partner_code,partner_name,partner_type,phone,address) VALUES(?,?,?,?,?)",
            [
                ("SUP-002", "한빛포장", "SUPPLIER", "02-555-0102", "경기도 화성시"),
                ("CUS-002", "우리유통", "CUSTOMER", "02-555-0202", "서울시 송파구"),
                ("CUS-003", "대성편의점", "CUSTOMER", "02-555-0203", "서울시 강남구"),
            ],
        )
        conn.execute("DELETE FROM equipment")
        conn.executemany(
            "INSERT INTO equipment(equipment_code,equipment_name,equipment_type,location) VALUES(?,?,?,?)",
            [
                ("EQ-PACK-01", "라면 포장 1호기", "포장설비", "1공장"),
                ("EQ-PACK-02", "라면 포장 2호기", "포장설비", "1공장"),
            ],
        )

        material_codes = ("RM-NOODLE", "RM-SOUP", "RM-PACK")
        material_ids = {
            code: conn.execute("SELECT item_id FROM item WHERE item_code=?", (code,)).fetchone()[0]
            for code in material_codes
        }
        products = conn.execute("SELECT item_id,item_code FROM item WHERE item_type='PRODUCT' ORDER BY item_id").fetchall()
        supplier = conn.execute("SELECT partner_id FROM business_partner WHERE partner_code='SUP-001'").fetchone()[0]
        customers = [r[0] for r in conn.execute("SELECT partner_id FROM business_partner WHERE partner_type IN ('CUSTOMER','BOTH') ORDER BY partner_id")]
        equipment_ids = [r[0] for r in conn.execute("SELECT equipment_id FROM equipment ORDER BY equipment_id")]
        defect_codes = [r[0] for r in conn.execute("SELECT defect_code_id FROM defect_code ORDER BY defect_code_id")]

        request_qty = 1000
        request_count = 3
        required_units = request_qty * request_count
        material_lots: dict[str, list[int]] = {code: [] for code in material_codes}

        # 면·스프·봉지는 모두 낱개 LOT이며 각 LOT 수량은 1이다.
        for material_index, code in enumerate(material_codes, 1):
            item_id = material_ids[code]
            po = conn.execute(
                "INSERT INTO purchase_order(purchase_order_no,supplier_id,order_date,expected_date,status,memo) VALUES(?,?,?,?,?,?)",
                (f"PO-UNIT-{material_index:02d}", supplier, base_date.isoformat(), base_date.isoformat(), "RECEIVED", "낱개 LOT 입고"),
            ).lastrowid
            detail = conn.execute(
                "INSERT INTO purchase_order_detail(purchase_order_id,material_item_id,order_qty,received_qty,unit_price) VALUES(?,?,?,?,?)",
                (po, item_id, required_units, required_units, rng.randint(80, 500)),
            ).lastrowid
            for unit_no in range(1, required_units + 1):
                lot_no = f"{code}-{base_date:%Y%m%d}-{unit_no:05d}"
                lot_id = conn.execute(
                    "INSERT INTO lot(lot_no,item_id,lot_type,initial_qty,qty,received_date,expire_date) VALUES(?,?, 'RECEIPT',1,1,?,?)",
                    (lot_no, item_id, base_date.isoformat(), (base_date + timedelta(days=180)).isoformat()),
                ).lastrowid
                conn.execute(
                    "INSERT INTO material_receipt(receipt_no,purchase_order_detail_id,material_lot_id,receipt_date,receipt_qty) VALUES(?,?,?,?,1)",
                    (f"RCV-{material_index:02d}-{unit_no:05d}", detail, lot_id, base_date.isoformat()),
                )
                material_lots[code].append(lot_id)

        material_cursor = 0
        for request_index in range(1, request_count + 1):
            production_date = base_date + timedelta(days=request_index)
            product_id, product_code = products[(request_index - 1) % len(products)]
            equipment_id = equipment_ids[(request_index - 1) % len(equipment_ids)]
            request_no = f"REQ-{production_date:%Y%m%d}-{request_index:03d}"
            request_id = conn.execute(
                "INSERT INTO production_request(request_no,item_id,requested_qty,request_date,status) VALUES(?,?,?,?, 'COMPLETED')",
                (request_no, product_id, request_qty, production_date.isoformat()),
            ).lastrowid
            product_lot_ids: list[int] = []

            for unit_no in range(1, request_qty + 1):
                serial = (request_index - 1) * request_qty + unit_no
                lot_id = conn.execute(
                    "INSERT INTO lot(lot_no,item_id,lot_type,initial_qty,qty,produced_date,expire_date) VALUES(?,?, 'PRODUCTION',1,1,?,?)",
                    (f"FG-{product_code[3:]}-{production_date:%Y%m%d}-{unit_no:05d}", product_id,
                     production_date.isoformat(), (production_date + timedelta(days=150)).isoformat()),
                ).lastrowid
                production_id = conn.execute(
                    """INSERT INTO production(production_no,item_id,output_lot_id,equipment_id,production_date,qty,
                    planned_start_time,planned_end_time,actual_start_time,actual_end_time,status)
                    VALUES(?,?,?,?,?,1,?,?,?,?, 'COMPLETED')""",
                    (f"PRD-{production_date:%Y%m%d}-{unit_no:05d}", product_id, lot_id, equipment_id,
                     production_date.isoformat(), f"{production_date} 08:00:00", f"{production_date} 17:00:00",
                     f"{production_date} 08:00:00", f"{production_date} 17:00:00"),
                ).lastrowid
                conn.execute(
                    "INSERT INTO production_request_unit(production_request_id,production_id) VALUES(?,?)",
                    (request_id, production_id),
                )
                # 완제품 1개 = 면 1 + 스프 1 + 봉지 1
                component_index = material_cursor + unit_no - 1
                for code in material_codes:
                    conn.execute(
                        "INSERT INTO production_material(production_id,material_lot_id,qty) VALUES(?,?,1)",
                        (production_id, material_lots[code][component_index]),
                    )
                product_lot_ids.append(lot_id)

                if unit_no <= 10:
                    conn.execute(
                        "INSERT INTO production_defect(production_id,defect_code_id,defect_qty,defect_date,memo) VALUES(?,?,?,?,?)",
                        (production_id, defect_codes[unit_no % len(defect_codes)], 1, production_date.isoformat(), "낱개 불량 샘플"),
                    )
            material_cursor += request_qty

            # 박스 하나는 서로 다른 완제품 낱개 LOT 40개로 구성한다.
            for box_index in range(request_qty // 40):
                box_id = conn.execute(
                    "INSERT INTO packing_box(box_no,box_qty,packed_date) VALUES(?,40,?)",
                    (f"BOX-{production_date:%Y%m%d}-{request_index:03d}-{box_index+1:04d}", production_date.isoformat()),
                ).lastrowid
                conn.executemany(
                    "INSERT INTO packing_box_detail(packing_box_id,product_lot_id) VALUES(?,?)",
                    [(box_id, lot_id) for lot_id in product_lot_ids[box_index * 40:(box_index + 1) * 40]],
                )

            planned, downtime = 540, rng.randint(20, 55)
            first_production = conn.execute(
                "SELECT production_id FROM production_request_unit WHERE production_request_id=? ORDER BY production_id LIMIT 1",
                (request_id,),
            ).fetchone()[0]
            conn.execute(
                "INSERT INTO equipment_operation(equipment_id,production_id,operation_date,planned_minutes,running_minutes,downtime_minutes,downtime_reason) VALUES(?,?,?,?,?,?,?)",
                (equipment_id, first_production, production_date.isoformat(), planned, planned - downtime, downtime, "품목 교체 및 세척"),
            )

            # 각 요청에서 800개를 낱개 LOT 단위로 출하한다.
            ship_qty = 800
            schedule = conn.execute(
                "INSERT INTO shipment_schedule(shipment_schedule_no,customer_id,item_id,scheduled_date,scheduled_qty) VALUES(?,?,?,?,?)",
                (f"SCH-UNIT-{request_index:03d}", customers[request_index % len(customers)], product_id,
                 (production_date + timedelta(days=1)).isoformat(), ship_qty),
            ).lastrowid
            shipment = conn.execute(
                "INSERT INTO shipment(shipment_no,shipment_schedule_id,customer_id,shipment_date,status,memo) VALUES(?,?,?,?, 'SHIPPED',?)",
                (f"SHP-UNIT-{request_index:03d}", schedule, customers[request_index % len(customers)],
                 (production_date + timedelta(days=1)).isoformat(), "낱개 LOT 출하"),
            ).lastrowid
            conn.executemany(
                "INSERT INTO shipment_detail(shipment_id,product_lot_id,shipment_qty) VALUES(?,?,1)",
                [(shipment, lot_id) for lot_id in product_lot_ids[:ship_qty]],
            )


def create_production_request(
    request_no: str, product_id: int, equipment_id: int | None,
    production_date: str, requested_qty: int,
) -> int:
    """생산요청을 완제품 낱개 LOT 및 1:1:1 원재료 투입으로 전개한다."""
    if requested_qty <= 0:
        raise ValueError("생산 요청수량은 1개 이상이어야 합니다.")
    material_codes = ("RM-NOODLE", "RM-SOUP", "RM-PACK")
    with transaction() as conn:
        material_lots: dict[str, list[int]] = {}
        for code in material_codes:
            rows = conn.execute("""
                SELECT l.lot_id FROM lot l JOIN item i ON i.item_id=l.item_id
                WHERE i.item_code=? AND l.lot_type='RECEIPT' AND l.qty=1
                ORDER BY l.expire_date,l.received_date,l.lot_id LIMIT ?
            """, (code, requested_qty)).fetchall()
            if len(rows) < requested_qty:
                raise ValueError(f"{code} 낱개 LOT 재고가 {requested_qty}개보다 부족합니다.")
            material_lots[code] = [row[0] for row in rows]

        request_id = conn.execute(
            "INSERT INTO production_request(request_no,item_id,requested_qty,request_date,status) VALUES(?,?,?,?, 'COMPLETED')",
            (request_no, product_id, requested_qty, production_date),
        ).lastrowid
        product_lots: list[int] = []
        for index in range(requested_qty):
            serial = index + 1
            lot_id = conn.execute(
                "INSERT INTO lot(lot_no,item_id,lot_type,initial_qty,qty,produced_date) VALUES(?,?, 'PRODUCTION',1,1,?)",
                (f"FG-{request_no}-{serial:05d}", product_id, production_date),
            ).lastrowid
            production_id = conn.execute(
                "INSERT INTO production(production_no,item_id,output_lot_id,equipment_id,production_date,qty,status) VALUES(?,?,?,?,?,1,'COMPLETED')",
                (f"PRD-{request_no}-{serial:05d}", product_id, lot_id, equipment_id, production_date),
            ).lastrowid
            conn.execute(
                "INSERT INTO production_request_unit(production_request_id,production_id) VALUES(?,?)",
                (request_id, production_id),
            )
            for code in material_codes:
                conn.execute(
                    "INSERT INTO production_material(production_id,material_lot_id,qty) VALUES(?,?,1)",
                    (production_id, material_lots[code][index]),
                )
            product_lots.append(lot_id)

        for box_index in range(requested_qty // 40):
            box_id = conn.execute(
                "INSERT INTO packing_box(box_no,box_qty,packed_date) VALUES(?,40,?)",
                (f"BOX-{request_no}-{box_index+1:04d}", production_date),
            ).lastrowid
            conn.executemany(
                "INSERT INTO packing_box_detail(packing_box_id,product_lot_id) VALUES(?,?)",
                [(box_id, lot_id) for lot_id in product_lots[box_index * 40:(box_index + 1) * 40]],
            )
        return int(request_id)
