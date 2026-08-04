from __future__ import annotations

import db
from domain.rules import BOX_SIZE, PRODUCT_MATERIAL_CODES


def create_request(request_no: str, product_id: int, equipment_id: int | None, production_date: str, quantity: int) -> int:
    """생산요청을 낱개 완제품 LOT와 1:1:1 원재료 LOT로 전개한다."""
    if quantity <= 0:
        raise ValueError("생산 요청수량은 1개 이상이어야 합니다.")

    with db.transaction() as connection:
        product = connection.execute(
            "SELECT item_code FROM item WHERE item_id=? AND item_type='PRODUCT'",
            (product_id,),
        ).fetchone()
        if product is None or product[0] not in PRODUCT_MATERIAL_CODES:
            raise ValueError("등록된 제품별 원재료 조합이 없습니다.")
        required_material_codes = PRODUCT_MATERIAL_CODES[product[0]]

        material_lots: dict[str, list[int]] = {}
        for code in required_material_codes:
            rows = connection.execute(
                """SELECT l.lot_id FROM lot l JOIN item i ON i.item_id=l.item_id
                WHERE i.item_code=? AND l.lot_type='RECEIPT' AND l.qty=1
                ORDER BY l.expire_date,l.received_date,l.lot_id LIMIT ?""",
                (code, quantity),
            ).fetchall()
            if len(rows) < quantity:
                raise ValueError(f"{code} 낱개 LOT 재고가 {quantity}개보다 부족합니다.")
            material_lots[code] = [row[0] for row in rows]

        request_id = connection.execute(
            "INSERT INTO production_request(request_no,item_id,requested_qty,request_date,status) VALUES(?,?,?,?, 'COMPLETED')",
            (request_no, product_id, quantity, production_date),
        ).lastrowid
        product_lots: list[int] = []
        for index in range(quantity):
            serial = index + 1
            lot_id = connection.execute(
                "INSERT INTO lot(lot_no,item_id,lot_type,initial_qty,qty,produced_date) VALUES(?,?, 'PRODUCTION',1,1,?)",
                (f"FG-{request_no}-{serial:05d}", product_id, production_date),
            ).lastrowid
            production_id = connection.execute(
                "INSERT INTO production(production_no,item_id,output_lot_id,equipment_id,production_date,qty,status) VALUES(?,?,?,?,?,1,'COMPLETED')",
                (f"PRD-{request_no}-{serial:05d}", product_id, lot_id, equipment_id, production_date),
            ).lastrowid
            connection.execute(
                "INSERT INTO production_request_unit(production_request_id,production_id) VALUES(?,?)",
                (request_id, production_id),
            )
            for code in required_material_codes:
                connection.execute(
                    "INSERT INTO production_material(production_id,material_lot_id,qty) VALUES(?,?,1)",
                    (production_id, material_lots[code][index]),
                )
            product_lots.append(lot_id)

        for box_index in range(quantity // BOX_SIZE):
            box_id = connection.execute(
                "INSERT INTO packing_box(box_no,box_qty,packed_date) VALUES(?,?,?)",
                (f"BOX-{request_no}-{box_index + 1:04d}", BOX_SIZE, production_date),
            ).lastrowid
            connection.executemany(
                "INSERT INTO packing_box_detail(packing_box_id,product_lot_id) VALUES(?,?)",
                [
                    (box_id, lot_id)
                    for lot_id in product_lots[box_index * BOX_SIZE:(box_index + 1) * BOX_SIZE]
                ],
            )
        return int(request_id)


def register_material(production_id: int, material_lot_id: int, quantity: float) -> int:
    return db.execute(
        "INSERT INTO production_material(production_id,material_lot_id,qty) VALUES(?,?,?)",
        (production_id, material_lot_id, quantity),
    )


def register_defect(production_id: int, defect_code_id: int, quantity: float, defect_date: str, memo: str) -> int:
    return db.execute(
        "INSERT INTO production_defect(production_id,defect_code_id,defect_qty,defect_date,memo) VALUES(?,?,?,?,?)",
        (production_id, defect_code_id, quantity, defect_date, memo),
    )
