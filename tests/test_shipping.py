import sys
from datetime import date
from pathlib import Path

import pytest


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import db
from domain.rules import BOX_SIZE
from repositories import shipping as shipping_repository
from services import production, shipping


@pytest.fixture(scope="module", autouse=True)
def seeded_shipping_data():
    db.seed_demo()


def _customer_and_stocked_product():
    customer_id = db.query(
        """SELECT partner_id FROM business_partner
           WHERE partner_type IN ('CUSTOMER','BOTH') ORDER BY partner_id LIMIT 1"""
    )[0][0]
    product_id, stock = db.query(
        """SELECT i.item_id,SUM(l.qty) stock
           FROM item i JOIN lot l ON l.item_id=i.item_id
           WHERE i.item_type='PRODUCT' AND l.lot_type='PRODUCTION'
           GROUP BY i.item_id HAVING stock>0 ORDER BY i.item_id LIMIT 1"""
    )[0]
    return int(customer_id), int(product_id), int(stock)


def test_schedule_based_shipping_deducts_product_inventory():
    customer_id, product_id, stock_before = _customer_and_stocked_product()
    box_quantity = 2
    schedule_id = shipping.create_schedule(
        customer_id, product_id, date.today().isoformat(), box_quantity
    )
    quantity = box_quantity * BOX_SIZE

    pending = shipping_repository.pending_schedules()
    target = pending[pending["출하계획ID"] == schedule_id].iloc[0]
    assert target["출고가능"] == 1
    assert target["미출하수량"] == quantity

    assert shipping.fulfill_schedule(
        schedule_id, date.today().isoformat()
    ) == quantity
    status, shipped_qty = db.query(
        """SELECT status,shipped_qty FROM shipment_schedule
           WHERE shipment_schedule_id=?""",
        (schedule_id,),
    )[0]
    assert (status, shipped_qty) == ("SHIPPED", quantity)
    stock_after = db.query(
        """SELECT COALESCE(SUM(qty),0) FROM lot
           WHERE item_id=? AND lot_type='PRODUCTION'""",
        (product_id,),
    )[0][0]
    assert stock_after == stock_before - quantity
    shipment_id = db.query(
        "SELECT shipment_id FROM shipment WHERE shipment_schedule_id=?",
        (schedule_id,),
    )[0][0]
    shipped_boxes = db.query(
        """SELECT sb.packing_box_id,COUNT(pbd.packing_box_detail_id)
           FROM shipment_box sb
           JOIN packing_box_detail pbd USING(packing_box_id)
           WHERE sb.shipment_id=? GROUP BY sb.packing_box_id""",
        (shipment_id,),
    )
    assert len(shipped_boxes) == box_quantity
    assert all(lot_count == BOX_SIZE for _, lot_count in shipped_boxes)
    completed = shipping_repository.completed_shipments()
    completed = completed[completed["출고번호"].str.contains(str(shipment_id).zfill(4))]
    assert completed.iloc[0]["출고박스"] == box_quantity
    assert completed.iloc[0]["출고박스번호"]


def test_shipping_is_blocked_when_product_inventory_is_insufficient():
    customer_id, product_id, stock = _customer_and_stocked_product()
    unavailable_box_quantity = stock // BOX_SIZE + 1
    schedule_id = shipping.create_schedule(
        customer_id,
        product_id,
        date.today().isoformat(),
        unavailable_box_quantity,
    )
    pending = shipping_repository.pending_schedules()
    target = pending[pending["출하계획ID"] == schedule_id].iloc[0]
    assert target["출고가능"] == 0
    with pytest.raises(ValueError, match="박스가 부족"):
        shipping.fulfill_schedule(schedule_id, date.today().isoformat())


def test_box_containing_defective_lot_is_not_shipped():
    customer_id = db.query(
        """SELECT partner_id FROM business_partner
           WHERE partner_type IN ('CUSTOMER','BOTH') ORDER BY partner_id LIMIT 1"""
    )[0][0]
    defective_box_id, production_id, product_id = db.query(
        """SELECT pb.packing_box_id,MIN(p.production_id),MIN(p.item_id)
           FROM packing_box pb
           JOIN packing_box_detail pbd USING(packing_box_id)
           JOIN lot l ON l.lot_id=pbd.product_lot_id
           JOIN production p ON p.output_lot_id=l.lot_id
           LEFT JOIN shipment_box sb USING(packing_box_id)
           WHERE sb.shipment_box_id IS NULL AND l.qty=1
             AND NOT EXISTS(
                 SELECT 1 FROM production_defect pd
                 WHERE pd.production_id=p.production_id
             )
           GROUP BY pb.packing_box_id
           HAVING COUNT(*)=?
           ORDER BY pb.packed_date,pb.packing_box_id
           LIMIT 1""",
        (BOX_SIZE,),
    )[0]
    defect_code_id = db.query(
        "SELECT defect_code_id FROM defect_code ORDER BY defect_code_id LIMIT 1"
    )[0][0]
    production.register_defect(
        production_id,
        defect_code_id,
        1,
        date.today().isoformat(),
        "출하 제외 검증",
    )

    schedule_id = shipping.create_schedule(
        customer_id, product_id, date.today().isoformat(), 1
    )
    shipping.fulfill_schedule(schedule_id, date.today().isoformat())
    shipment_id = db.query(
        "SELECT shipment_id FROM shipment WHERE shipment_schedule_id=?",
        (schedule_id,),
    )[0][0]

    assert db.query(
        """SELECT COUNT(*) FROM shipment_box
           WHERE shipment_id=? AND packing_box_id=?""",
        (shipment_id, defective_box_id),
    )[0][0] == 0
    assert db.query(
        """SELECT COUNT(*)
           FROM shipment_detail sd
           JOIN production p ON p.output_lot_id=sd.product_lot_id
           JOIN production_defect pd ON pd.production_id=p.production_id
           WHERE sd.shipment_id=?""",
        (shipment_id,),
    )[0][0] == 0
