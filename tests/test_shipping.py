import sys
from datetime import date
from pathlib import Path

import pytest


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import db
from domain.rules import BOX_SIZE
from repositories import shipping as shipping_repository
from services import shipping


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
    assert not shipping_repository.completed_shipments().empty


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
    with pytest.raises(ValueError, match="재고가 부족"):
        shipping.fulfill_schedule(schedule_id, date.today().isoformat())
