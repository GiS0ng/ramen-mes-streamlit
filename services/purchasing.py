from __future__ import annotations

from datetime import date

import db


def create_purchase_order(
    supplier_id: int,
    item_id: int,
    quantity: int,
    expected_date: date,
) -> int:
    if quantity <= 0:
        raise ValueError("발주량은 1개 이상이어야 합니다.")

    with db.transaction() as connection:
        material = connection.execute(
            "SELECT 1 FROM item WHERE item_id=? AND item_type='MATERIAL' AND is_active='Y'",
            (item_id,),
        ).fetchone()
        if material is None:
            raise ValueError("사용 가능한 원재료를 선택해 주세요.")
        today = date.today()
        next_id = connection.execute(
            "SELECT COALESCE(MAX(purchase_order_id),0)+1 FROM purchase_order"
        ).fetchone()[0]
        order_no = f"PO-{today:%Y%m%d}-{next_id:04d}"
        cursor = connection.execute(
            """INSERT INTO purchase_order(
                   purchase_order_no,supplier_id,order_date,expected_date,status,memo
               ) VALUES(?,?,?,?, 'ORDERED',?)""",
            (
                order_no, supplier_id, today.isoformat(), expected_date.isoformat(),
                "현장 확인 후 입고 처리",
            ),
        )
        connection.execute(
            "INSERT INTO purchase_order_detail(purchase_order_id,material_item_id,order_qty,unit_price) VALUES(?,?,?,0)",
            (cursor.lastrowid, item_id, quantity),
        )
        return int(cursor.lastrowid)


def receive_purchase_order(order_detail_id: int, receipt_date: date) -> int:
    """현장에서 확인한 미입고 잔량 전체를 낱개 원재료 LOT로 입고한다."""
    with db.transaction() as connection:
        detail = connection.execute(
            """SELECT pod.material_item_id,pod.order_qty,pod.received_qty,
                      pod.purchase_order_id,po.purchase_order_no
               FROM purchase_order_detail pod
               JOIN purchase_order po USING(purchase_order_id)
               WHERE pod.purchase_order_detail_id=? AND po.status<>'CANCELED'""",
            (order_detail_id,),
        ).fetchone()
        if detail is None:
            raise ValueError("입고할 발주서를 찾을 수 없습니다.")

        remaining = detail[1] - detail[2]
        if remaining <= 0:
            raise ValueError("이미 입고 완료된 발주서입니다.")
        if not float(remaining).is_integer():
            raise ValueError("낱개 LOT 입고는 정수 수량만 처리할 수 있습니다.")

        receipt_day = receipt_date.isoformat()
        for serial in range(1, int(remaining) + 1):
            lot_no = f"RM-{receipt_date:%Y%m%d}-{order_detail_id:06d}-{serial:05d}"
            receipt_no = f"RCV-{receipt_date:%Y%m%d}-{order_detail_id:06d}-{serial:05d}"
            lot_id = connection.execute(
                """INSERT INTO lot(
                       lot_no,item_id,lot_type,initial_qty,qty,received_date
                   ) VALUES(?,?, 'RECEIPT',1,1,?)""",
                (lot_no, detail[0], receipt_day),
            ).lastrowid
            connection.execute(
                """INSERT INTO material_receipt(
                       receipt_no,purchase_order_detail_id,material_lot_id,receipt_date,receipt_qty
                   ) VALUES(?,?,?,?,1)""",
                (receipt_no, order_detail_id, lot_id, receipt_day),
            )

        connection.execute(
            "UPDATE purchase_order_detail SET received_qty=order_qty WHERE purchase_order_detail_id=?",
            (order_detail_id,),
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
        return int(remaining)


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
