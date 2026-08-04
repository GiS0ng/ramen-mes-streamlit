import sys
from datetime import date, timedelta
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import db
from services import purchasing


def test_purchase_order_and_field_receipt_flow():
    db.reset_demo()
    try:
        supplier_id = db.query(
            "SELECT partner_id FROM business_partner WHERE partner_code='SUP-001'"
        )[0][0]
        material_id = db.query(
            "SELECT item_id FROM item WHERE item_code='RM-SOUP-SPICY'"
        )[0][0]
        expected_date = date.today() + timedelta(days=7)

        order_id = purchasing.create_purchase_order(
            supplier_id, material_id, 3, expected_date
        )
        order = db.query(
            """SELECT order_date,expected_date,status
               FROM purchase_order WHERE purchase_order_id=?""",
            (order_id,),
        )[0]
        assert tuple(order) == (
            date.today().isoformat(), expected_date.isoformat(), "ORDERED"
        )

        detail_id = db.query(
            """SELECT purchase_order_detail_id
               FROM purchase_order_detail WHERE purchase_order_id=?""",
            (order_id,),
        )[0][0]
        received_count = purchasing.receive_purchase_order(detail_id, date.today())
        assert received_count == 3
        assert tuple(db.query(
            """SELECT order_qty,received_qty
               FROM purchase_order_detail WHERE purchase_order_detail_id=?""",
            (detail_id,),
        )[0]) == (3, 3)
        assert db.query(
            "SELECT status FROM purchase_order WHERE purchase_order_id=?", (order_id,)
        )[0][0] == "RECEIVED"
        assert db.query(
            """SELECT COUNT(*) FROM material_receipt
               WHERE purchase_order_detail_id=? AND receipt_qty=1""",
            (detail_id,),
        )[0][0] == 3
        assert db.query(
            """SELECT COUNT(*) FROM lot l
               JOIN material_receipt mr ON mr.material_lot_id=l.lot_id
               WHERE mr.purchase_order_detail_id=?
                 AND l.initial_qty=1 AND l.qty=1 AND l.lot_type='RECEIPT'""",
            (detail_id,),
        )[0][0] == 3
    finally:
        db.reset_demo()
