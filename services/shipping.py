from __future__ import annotations

import db


def create_schedule(schedule_no: str, customer_id: int, item_id: int, scheduled_date: str, quantity: float) -> int:
    return db.execute(
        "INSERT INTO shipment_schedule(shipment_schedule_no,customer_id,item_id,scheduled_date,scheduled_qty) VALUES(?,?,?,?,?)",
        (schedule_no, customer_id, item_id, scheduled_date, quantity),
    )


def create_shipment(shipment_no: str, schedule_id: int, shipment_date: str) -> int:
    rows = db.query("SELECT customer_id FROM shipment_schedule WHERE shipment_schedule_id=?", (schedule_id,))
    if not rows:
        raise ValueError("출하계획을 찾을 수 없습니다.")
    return db.execute(
        "INSERT INTO shipment(shipment_no,shipment_schedule_id,customer_id,shipment_date) VALUES(?,?,?,?)",
        (shipment_no, schedule_id, rows[0][0], shipment_date),
    )


def ship_lot(shipment_id: int, product_lot_id: int, quantity: float) -> int:
    return db.execute(
        "INSERT INTO shipment_detail(shipment_id,product_lot_id,shipment_qty) VALUES(?,?,?)",
        (shipment_id, product_lot_id, quantity),
    )
