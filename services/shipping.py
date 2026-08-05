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

        product_lots = connection.execute(
            """SELECT lot_id,qty FROM lot
               WHERE item_id=? AND lot_type='PRODUCTION' AND qty>0
               ORDER BY produced_date,lot_id""",
            (item_id,),
        ).fetchall()
        stock_quantity = sum(float(row[1]) for row in product_lots)
        if stock_quantity < remaining_quantity:
            raise ValueError(
                f"완제품 재고가 부족합니다. 필요 {remaining_quantity}개, "
                f"현재 {int(stock_quantity)}개"
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

        quantity_to_ship = float(remaining_quantity)
        for lot_id, lot_quantity in product_lots:
            if quantity_to_ship <= 0:
                break
            shipped_quantity = min(float(lot_quantity), quantity_to_ship)
            connection.execute(
                """INSERT INTO shipment_detail(
                       shipment_id,product_lot_id,shipment_qty
                   ) VALUES(?,?,?)""",
                (shipment_id, lot_id, shipped_quantity),
            )
            quantity_to_ship -= shipped_quantity

        connection.execute(
            "UPDATE shipment SET status='SHIPPED' WHERE shipment_id=?",
            (shipment_id,),
        )
        return remaining_quantity
