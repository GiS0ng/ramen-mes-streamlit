from __future__ import annotations

import random
from calendar import monthrange
from datetime import date, timedelta

import db
from domain.rules import (
    BOX_SIZE,
    DEMO_REQUEST_COUNT,
    DEMO_REQUEST_QUANTITY,
    DEMO_SHIPMENT_QUANTITY,
    MATERIAL_ITEM_CODES,
    PACKAGING_CAPACITY_PER_MINUTE,
    PRODUCT_MATERIAL_CODES,
    RAW_MATERIAL_SAFETY_STOCK,
)


def _month_date(reference_date: date, months_ago: int) -> date:
    """기준일을 넘지 않는 해당 월의 대표 작업일을 반환한다."""
    month_index = reference_date.year * 12 + reference_date.month - 1 - months_ago
    year, zero_based_month = divmod(month_index, 12)
    month = zero_based_month + 1
    day = min(reference_date.day, 10, monthrange(year, month)[1])
    return date(year, month, day)


def seed_demo(days: int = 90, seed: int = 20260803) -> None:
    """현재 월을 포함한 최근 3개월의 MES 연계 더미 데이터를 생성한다."""
    del days  # 이전 공개 호출 규격을 유지하며 데이터 범위는 최근 3개월로 고정한다.
    db.reset_demo()
    rng = random.Random(seed)
    production_dates = [
        _month_date(date.today(), months_ago)
        for months_ago in range(DEMO_REQUEST_COUNT - 1, -1, -1)
    ]

    with db.transaction() as connection:
        connection.executemany(
            "INSERT OR IGNORE INTO item(item_code,item_name,item_type,unit,safety_stock) VALUES(?,?,?,?,?)",
            [
                ("FG-SPICY", "매운맛 라면", "PRODUCT", "EA", RAW_MATERIAL_SAFETY_STOCK),
                ("FG-MILD", "순한맛 라면", "PRODUCT", "EA", RAW_MATERIAL_SAFETY_STOCK),
            ],
        )
        connection.executemany(
            "INSERT OR IGNORE INTO business_partner(partner_code,partner_name,partner_type,phone,address) VALUES(?,?,?,?,?)",
            [
                ("SUP-002", "한빛포장", "SUPPLIER", "02-555-0102", "경기도 화성시"),
                ("CUS-002", "우리유통", "CUSTOMER", "02-555-0202", "서울시 송파구"),
                ("CUS-003", "대성편의점", "CUSTOMER", "02-555-0203", "서울시 강남구"),
            ],
        )
        connection.execute("DELETE FROM equipment")
        connection.executemany(
            """INSERT INTO equipment(
                   equipment_code,equipment_name,equipment_type,location,capacity_per_minute
               ) VALUES(?,?,?,?,?)""",
            [
                (
                    "EQ-PACK-01", "라면 포장 1호기", "포장설비", "1공장",
                    PACKAGING_CAPACITY_PER_MINUTE,
                ),
                (
                    "EQ-PACK-02", "라면 포장 2호기", "포장설비", "1공장",
                    PACKAGING_CAPACITY_PER_MINUTE,
                ),
            ],
        )

        material_ids = {
            code: connection.execute("SELECT item_id FROM item WHERE item_code=?", (code,)).fetchone()[0]
            for code in MATERIAL_ITEM_CODES
        }
        products = connection.execute(
            "SELECT item_id,item_code FROM item WHERE item_type='PRODUCT' ORDER BY item_id"
        ).fetchall()
        product_runs = [
            (production_date, *products[index % len(products)])
            for index, production_date in enumerate(production_dates)
        ]
        supplier = connection.execute(
            "SELECT partner_id FROM business_partner WHERE partner_code='SUP-001'"
        ).fetchone()[0]
        customers = [
            row[0]
            for row in connection.execute(
                "SELECT partner_id FROM business_partner WHERE partner_type IN ('CUSTOMER','BOTH') ORDER BY partner_id"
            )
        ]
        equipment_ids = [row[0] for row in connection.execute("SELECT equipment_id FROM equipment ORDER BY equipment_id")]
        defect_codes = [row[0] for row in connection.execute("SELECT defect_code_id FROM defect_code ORDER BY defect_code_id")]

        material_lots: dict[str, list[int]] = {code: [] for code in MATERIAL_ITEM_CODES}

        for material_index, code in enumerate(MATERIAL_ITEM_CODES, 1):
            item_id = material_ids[code]
            demand_dates = [
                production_date
                for production_date, _, product_code in product_runs
                if code in PRODUCT_MATERIAL_CODES[product_code]
            ]
            for batch_index, production_date in enumerate(demand_dates, 1):
                receipt_date = production_date.replace(day=1)
                order_id = connection.execute(
                    "INSERT INTO purchase_order(purchase_order_no,supplier_id,order_date,expected_date,status,memo) VALUES(?,?,?,?,?,?)",
                    (
                        f"PO-{receipt_date:%Y%m}-{material_index:02d}", supplier,
                        receipt_date.isoformat(), receipt_date.isoformat(), "RECEIVED",
                        "월별 낱개 LOT 입고",
                    ),
                ).lastrowid
                detail_id = connection.execute(
                    "INSERT INTO purchase_order_detail(purchase_order_id,material_item_id,order_qty,received_qty,unit_price) VALUES(?,?,?,?,?)",
                    (order_id, item_id, DEMO_REQUEST_QUANTITY, DEMO_REQUEST_QUANTITY, rng.randint(80, 500)),
                ).lastrowid
                for unit_no in range(1, DEMO_REQUEST_QUANTITY + 1):
                    lot_id = connection.execute(
                        "INSERT INTO lot(lot_no,item_id,lot_type,initial_qty,qty,received_date,expire_date) VALUES(?,?, 'RECEIPT',1,1,?,?)",
                        (
                            f"{code}-{receipt_date:%Y%m%d}-{unit_no:05d}",
                            item_id,
                            receipt_date.isoformat(),
                            (receipt_date + timedelta(days=180)).isoformat(),
                        ),
                    ).lastrowid
                    connection.execute(
                        "INSERT INTO material_receipt(receipt_no,purchase_order_detail_id,material_lot_id,receipt_date,receipt_qty) VALUES(?,?,?,?,1)",
                        (
                            f"RCV-{material_index:02d}-{batch_index:02d}-{unit_no:05d}",
                            detail_id, lot_id, receipt_date.isoformat(),
                        ),
                    )
                    material_lots[code].append(lot_id)

        material_offsets = {code: 0 for code in MATERIAL_ITEM_CODES}
        for request_index, (production_date, product_id, product_code) in enumerate(product_runs, 1):
            equipment_id = equipment_ids[(request_index - 1) % len(equipment_ids)]
            required_material_codes = PRODUCT_MATERIAL_CODES[product_code]
            request_no = f"REQ-{production_date:%Y%m%d}-{request_index:03d}"
            request_id = connection.execute(
                """INSERT INTO production_request(
                       request_no,item_id,equipment_id,requested_qty,request_date,status
                   ) VALUES(?,?,?,?,?, 'COMPLETED')""",
                (
                    request_no, product_id, equipment_id,
                    DEMO_REQUEST_QUANTITY, production_date.isoformat(),
                ),
            ).lastrowid
            product_lot_ids: list[int] = []

            for unit_no in range(1, DEMO_REQUEST_QUANTITY + 1):
                lot_id = connection.execute(
                    "INSERT INTO lot(lot_no,item_id,lot_type,initial_qty,qty,produced_date,expire_date) VALUES(?,?, 'PRODUCTION',1,1,?,?)",
                    (
                        f"FG-{product_code[3:]}-{production_date:%Y%m%d}-{unit_no:05d}",
                        product_id,
                        production_date.isoformat(),
                        (production_date + timedelta(days=150)).isoformat(),
                    ),
                ).lastrowid
                production_id = connection.execute(
                    """INSERT INTO production(production_no,item_id,output_lot_id,equipment_id,production_date,qty,
                    planned_start_time,planned_end_time,actual_start_time,actual_end_time,status)
                    VALUES(?,?,?,?,?,1,?,?,?,?, 'COMPLETED')""",
                    (
                        f"PRD-{production_date:%Y%m%d}-{unit_no:05d}",
                        product_id,
                        lot_id,
                        equipment_id,
                        production_date.isoformat(),
                        f"{production_date} 08:00:00",
                        f"{production_date} 17:00:00",
                        f"{production_date} 08:00:00",
                        f"{production_date} 17:00:00",
                    ),
                ).lastrowid
                connection.execute(
                    "INSERT INTO production_request_unit(production_request_id,production_id) VALUES(?,?)",
                    (request_id, production_id),
                )
                for code in required_material_codes:
                    component_index = material_offsets[code] + unit_no - 1
                    connection.execute(
                        "INSERT INTO production_material(production_id,material_lot_id,qty) VALUES(?,?,1)",
                        (production_id, material_lots[code][component_index]),
                    )
                product_lot_ids.append(lot_id)

                if unit_no <= 10:
                    connection.execute(
                        "INSERT INTO production_defect(production_id,defect_code_id,defect_qty,defect_date,memo) VALUES(?,?,?,?,?)",
                        (production_id, defect_codes[unit_no % len(defect_codes)], 1, production_date.isoformat(), "낱개 불량 샘플"),
                    )
            for code in required_material_codes:
                material_offsets[code] += DEMO_REQUEST_QUANTITY

            for box_index in range(DEMO_REQUEST_QUANTITY // BOX_SIZE):
                box_id = connection.execute(
                    "INSERT INTO packing_box(box_no,box_qty,packed_date) VALUES(?,?,?)",
                    (
                        f"BOX-{production_date:%Y%m%d}-{request_index:03d}-{box_index + 1:04d}",
                        BOX_SIZE,
                        production_date.isoformat(),
                    ),
                ).lastrowid
                connection.executemany(
                    "INSERT INTO packing_box_detail(packing_box_id,product_lot_id) VALUES(?,?)",
                    [
                        (box_id, lot_id)
                        for lot_id in product_lot_ids[box_index * BOX_SIZE:(box_index + 1) * BOX_SIZE]
                    ],
                )

            downtime_minutes = rng.randint(20, 55)
            running_minutes = int(DEMO_REQUEST_QUANTITY / PACKAGING_CAPACITY_PER_MINUTE)
            planned_minutes = running_minutes + downtime_minutes
            first_production = connection.execute(
                "SELECT production_id FROM production_request_unit WHERE production_request_id=? ORDER BY production_id LIMIT 1",
                (request_id,),
            ).fetchone()[0]
            connection.execute(
                "INSERT INTO equipment_operation(equipment_id,production_id,operation_date,planned_minutes,running_minutes,downtime_minutes,downtime_reason) VALUES(?,?,?,?,?,?,?)",
                (
                    equipment_id,
                    first_production,
                    production_date.isoformat(),
                    planned_minutes,
                    running_minutes,
                    downtime_minutes,
                    "품목 교체 및 세척",
                ),
            )

            schedule_id = connection.execute(
                "INSERT INTO shipment_schedule(shipment_schedule_no,customer_id,item_id,scheduled_date,scheduled_qty) VALUES(?,?,?,?,?)",
                (
                    f"SCH-UNIT-{request_index:03d}",
                    customers[request_index % len(customers)],
                    product_id,
                    production_date.isoformat(),
                    DEMO_SHIPMENT_QUANTITY,
                ),
            ).lastrowid
            shipment_id = connection.execute(
                "INSERT INTO shipment(shipment_no,shipment_schedule_id,customer_id,shipment_date,status,memo) VALUES(?,?,?,?, 'SHIPPED',?)",
                (
                    f"SHP-UNIT-{request_index:03d}",
                    schedule_id,
                    customers[request_index % len(customers)],
                    production_date.isoformat(),
                    "낱개 LOT 출하",
                ),
            ).lastrowid
            connection.executemany(
                "INSERT INTO shipment_detail(shipment_id,product_lot_id,shipment_qty) VALUES(?,?,1)",
                [(shipment_id, lot_id) for lot_id in product_lot_ids[:DEMO_SHIPMENT_QUANTITY]],
            )
