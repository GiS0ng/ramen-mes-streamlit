from __future__ import annotations

from datetime import date

import db
from domain.rules import BOX_SIZE


def create_schedule(
    customer_id: int,
    item_id: int,
    scheduled_date: str,
    box_quantity: int,
) -> int:
    if box_quantity <= 0:
        raise ValueError("출하 수량은 1박스 이상이어야 합니다.")
    quantity = box_quantity * BOX_SIZE
    with db.transaction() as connection:
        customer = connection.execute(
            """SELECT 1 FROM business_partner
               WHERE partner_id=? AND partner_type IN ('CUSTOMER','BOTH')
                 AND is_active='Y'""",
            (customer_id,),
        ).fetchone()
        product = connection.execute(
            """SELECT 1 FROM item
               WHERE item_id=? AND item_type='PRODUCT' AND is_active='Y'""",
            (item_id,),
        ).fetchone()
        if customer is None:
            raise ValueError("사용 가능한 고객사를 선택해 주세요.")
        if product is None:
            raise ValueError("사용 가능한 완제품을 선택해 주세요.")

        next_id = int(connection.execute(
            "SELECT COALESCE(MAX(shipment_schedule_id),0)+1 FROM shipment_schedule"
        ).fetchone()[0])
        schedule_no = f"SCH-{date.fromisoformat(scheduled_date):%Y%m%d}-{next_id:04d}"
        cursor = connection.execute(
            """INSERT INTO shipment_schedule(
                   shipment_schedule_no,customer_id,item_id,
                   scheduled_date,scheduled_qty
               ) VALUES(?,?,?,?,?)""",
            (schedule_no, customer_id, item_id, scheduled_date, quantity),
        )
        return int(cursor.lastrowid)


def fulfill_schedule(schedule_id: int, shipment_date: str) -> int:
    """미출하 계획을 제품 LOT 선입선출 방식으로 전량 출고한다."""
    with db.transaction() as connection:
        schedule = connection.execute(
            """SELECT customer_id,item_id,scheduled_qty-shipped_qty
               FROM shipment_schedule
               WHERE shipment_schedule_id=?
                 AND status IN ('PLANNED','PARTIAL_SHIPPED')""",
            (schedule_id,),
        ).fetchone()
        if schedule is None:
            raise ValueError("출고 가능한 미출하 계획을 찾을 수 없습니다.")
        customer_id, item_id, remaining_quantity = schedule
        remaining_quantity = int(remaining_quantity)

        if remaining_quantity % BOX_SIZE:
            raise ValueError("출하계획 수량은 40개입 박스 단위여야 합니다.")
        required_box_quantity = remaining_quantity // BOX_SIZE
        available_boxes = connection.execute(
            """SELECT pb.packing_box_id
               FROM packing_box pb
               JOIN packing_box_detail pbd USING(packing_box_id)
               JOIN lot l ON l.lot_id=pbd.product_lot_id
               JOIN production p ON p.output_lot_id=l.lot_id
               LEFT JOIN shipment_box sb USING(packing_box_id)
               WHERE p.item_id=? AND sb.shipment_box_id IS NULL
                 AND NOT EXISTS(
                     SELECT 1 FROM production_defect pd
                     WHERE pd.production_id=p.production_id
                 )
               GROUP BY pb.packing_box_id
               HAVING COUNT(*)=?
                  AND SUM(CASE WHEN l.qty>=1 THEN 1 ELSE 0 END)=?
               ORDER BY pb.packed_date,pb.packing_box_id
               LIMIT ?""",
            (item_id, BOX_SIZE, BOX_SIZE, required_box_quantity),
        ).fetchall()
        if len(available_boxes) < required_box_quantity:
            raise ValueError(
                f"출고 가능한 완제품 박스가 부족합니다. "
                f"필요 {required_box_quantity}박스, 현재 {len(available_boxes)}박스"
            )

        next_id = int(connection.execute(
            "SELECT COALESCE(MAX(shipment_id),0)+1 FROM shipment"
        ).fetchone()[0])
        shipment_no = f"SHP-{date.fromisoformat(shipment_date):%Y%m%d}-{next_id:04d}"
        shipment_id = int(connection.execute(
            """INSERT INTO shipment(
                   shipment_no,shipment_schedule_id,customer_id,
                   shipment_date,status
               ) VALUES(?,?,?,?, 'READY')""",
            (shipment_no, schedule_id, customer_id, shipment_date),
        ).lastrowid)

        for (packing_box_id,) in available_boxes:
            connection.execute(
                """INSERT INTO shipment_box(shipment_id,packing_box_id)
                   VALUES(?,?)""",
                (shipment_id, packing_box_id),
            )
            product_lots = connection.execute(
                """SELECT product_lot_id FROM packing_box_detail
                   WHERE packing_box_id=? ORDER BY packing_box_detail_id""",
                (packing_box_id,),
            ).fetchall()
            connection.executemany(
                """INSERT INTO shipment_detail(
                       shipment_id,product_lot_id,shipment_qty
                   ) VALUES(?,?,1)""",
                [(shipment_id, int(row[0])) for row in product_lots],
            )

        connection.execute(
            "UPDATE shipment SET status='SHIPPED' WHERE shipment_id=?",
            (shipment_id,),
        )
        return remaining_quantity
