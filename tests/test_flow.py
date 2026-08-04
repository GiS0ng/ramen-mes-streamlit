import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import db


def test_complete_material_to_shipment_flow():
    db.reset_demo()
    try:
        with db.transaction() as c:
            sup = c.execute("SELECT partner_id FROM business_partner WHERE partner_code='SUP-001'").fetchone()[0]
            mat = c.execute("SELECT item_id FROM item WHERE item_code='RM-NOODLE'").fetchone()[0]
            product = c.execute("SELECT item_id FROM item WHERE item_code='FG-RAMEN'").fetchone()[0]
            customer = c.execute("SELECT partner_id FROM business_partner WHERE partner_code='CUS-001'").fetchone()[0]
            equipment = c.execute("SELECT equipment_id FROM equipment").fetchone()[0]
            po = c.execute("INSERT INTO purchase_order(purchase_order_no,supplier_id,order_date) VALUES('PO-T',?,'2026-08-03')", (sup,)).lastrowid
            pod = c.execute("INSERT INTO purchase_order_detail(purchase_order_id,material_item_id,order_qty) VALUES(?,?,100)", (po, mat)).lastrowid
            material_lot = c.execute("INSERT INTO lot(lot_no,item_id,lot_type,initial_qty,qty,received_date) VALUES('ML-T',?,'RECEIPT',100,100,'2026-08-03')", (mat,)).lastrowid
            c.execute("INSERT INTO material_receipt(receipt_no,purchase_order_detail_id,material_lot_id,receipt_date,receipt_qty) VALUES('R-T',?,?,'2026-08-03',100)", (pod, material_lot))
            product_lot = c.execute("INSERT INTO lot(lot_no,item_id,lot_type,initial_qty,qty,produced_date) VALUES('PL-T',?,'PRODUCTION',80,80,'2026-08-03')", (product,)).lastrowid
            production = c.execute("INSERT INTO production(production_no,item_id,output_lot_id,equipment_id,production_date,qty,status) VALUES('P-T',?,?,?,'2026-08-03',80,'COMPLETED')", (product, product_lot, equipment)).lastrowid
            c.execute("INSERT INTO production_material(production_id,material_lot_id,qty) VALUES(?,?,90)", (production, material_lot))
            schedule = c.execute("INSERT INTO shipment_schedule(shipment_schedule_no,customer_id,item_id,scheduled_date,scheduled_qty) VALUES('SC-T',?,?,'2026-08-04',50)", (customer, product)).lastrowid
            shipment = c.execute("INSERT INTO shipment(shipment_no,shipment_schedule_id,customer_id,shipment_date) VALUES('SH-T',?,?,'2026-08-04')", (schedule, customer)).lastrowid
            c.execute("INSERT INTO shipment_detail(shipment_id,product_lot_id,shipment_qty) VALUES(?,?,30)", (shipment, product_lot))

        assert db.query("SELECT qty FROM lot WHERE lot_no='ML-T'")[0][0] == 10
        assert db.query("SELECT qty FROM lot WHERE lot_no='PL-T'")[0][0] == 50
        schedule_state = db.query("SELECT shipped_qty,status FROM shipment_schedule WHERE shipment_schedule_no='SC-T'")[0]
        assert tuple(schedule_state) == (30, "PARTIAL_SHIPPED")
        assert len(db.query("SELECT * FROM v_shipment_production_trace WHERE production_no='P-T'")) == 1
    finally:
        db.reset_demo()


if __name__ == "__main__":
    test_complete_material_to_shipment_flow()
    print("integration-ok")
