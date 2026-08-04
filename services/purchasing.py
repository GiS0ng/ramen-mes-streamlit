from __future__ import annotations

from datetime import date

import db


def create_purchase_order(
    order_no: str,
    supplier_id: int,
    order_date: date,
    item_id: int,
    quantity: float,
    unit_price: float,
    memo: str,
) -> int:
    with db.transaction() as connection:
        cursor = connection.execute(
            "INSERT INTO purchase_order(purchase_order_no,supplier_id,order_date,memo) VALUES(?,?,?,?)",
            (order_no, supplier_id, order_date.isoformat(), memo),
        )
        connection.execute(
            "INSERT INTO purchase_order_detail(purchase_order_id,material_item_id,order_qty,unit_price) VALUES(?,?,?,?)",
            (cursor.lastrowid, item_id, quantity, unit_price),
        )
        return int(cursor.lastrowid)


def receive_material(
    order_detail_id: int,
    receipt_no: str,
    lot_no: str,
    receipt_date: date,
    quantity: float,
    expire_date: date | None,
) -> int:
    with db.transaction() as connection:
        detail = connection.execute(
            "SELECT material_item_id,order_qty,received_qty,purchase_order_id FROM purchase_order_detail WHERE purchase_order_detail_id=?",
            (order_detail_id,),
        ).fetchone()
        if detail is None:
            raise ValueError("발주상세를 찾을 수 없습니다.")
        if detail[2] + quantity > detail[1]:
            raise ValueError("미입고 잔량을 초과할 수 없습니다.")

        lot = connection.execute(
            "INSERT INTO lot(lot_no,item_id,lot_type,initial_qty,qty,received_date,expire_date) VALUES(?,?,?,?,?,?,?)",
            (
                lot_no,
                detail[0],
                "RECEIPT",
                quantity,
                quantity,
                receipt_date.isoformat(),
                expire_date.isoformat() if expire_date else None,
            ),
        )
        connection.execute(
            "INSERT INTO material_receipt(receipt_no,purchase_order_detail_id,material_lot_id,receipt_date,receipt_qty) VALUES(?,?,?,?,?)",
            (receipt_no, order_detail_id, lot.lastrowid, receipt_date.isoformat(), quantity),
        )
        connection.execute(
            "UPDATE purchase_order_detail SET received_qty=received_qty+? WHERE purchase_order_detail_id=?",
            (quantity, order_detail_id),
        )
        connection.execute(
            """UPDATE purchase_order
               SET status=CASE WHEN NOT EXISTS(
                   SELECT 1 FROM purchase_order_detail
                   WHERE purchase_order_id=? AND received_qty<order_qty
               ) THEN 'RECEIVED' ELSE 'PARTIAL_RECEIVED' END
               WHERE purchase_order_id=?""",
            (detail[3], detail[3]),
        )
        return int(lot.lastrowid)
