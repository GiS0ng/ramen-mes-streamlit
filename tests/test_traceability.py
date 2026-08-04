from __future__ import annotations

import pytest

import db
from repositories import traceability


@pytest.fixture(scope="module", autouse=True)
def seeded_traceability_data():
    db.seed_demo()


def _shipped_raw_lot():
    return db.query(
        """SELECT pm.material_lot_id,s.customer_id,s.shipment_date
        FROM production_material pm
        JOIN production p USING(production_id)
        JOIN shipment_detail sd ON sd.product_lot_id=p.output_lot_id
        JOIN shipment s USING(shipment_id)
        ORDER BY s.shipment_date,pm.material_lot_id
        LIMIT 1"""
    )[0]


def test_raw_material_to_products_filters_production_date():
    raw_lot_id, _, _ = _shipped_raw_lot()
    rows = traceability.raw_material_to_products(raw_lot_id, "1900-01-01", "2999-12-31")
    assert not rows.empty
    assert {"원재료LOT", "생산번호", "생산일", "완제품LOT", "제품"}.issubset(rows.columns)
    assert traceability.raw_material_to_products(
        raw_lot_id, "1900-01-01", "1900-01-02"
    ).empty


def test_raw_material_lot_options_filter_name_and_receipt_date():
    item_id, item_name, receipt_date = db.query(
        """SELECT i.item_id,i.item_name,l.received_date
        FROM lot l JOIN item i USING(item_id)
        WHERE l.lot_type='RECEIPT'
        ORDER BY l.lot_id LIMIT 1"""
    )[0]
    options = traceability.raw_material_options(item_id, receipt_date, receipt_date)
    assert options
    assert all(item_name in label for label in options)
    assert not traceability.raw_material_options(item_id, "1900-01-01", "1900-01-02")


def test_raw_material_to_shipments_filters_customer_and_date():
    raw_lot_id, customer_id, shipment_date = _shipped_raw_lot()
    rows = traceability.raw_material_to_shipments(
        raw_lot_id, shipment_date, shipment_date, customer_id
    )
    assert not rows.empty
    expected_customer = db.query(
        "SELECT partner_name FROM business_partner WHERE partner_id=?", (customer_id,)
    )[0][0]
    assert set(rows["고객사"]) == {expected_customer}
    assert set(rows["출하일"]) == {shipment_date}


def test_raw_material_to_shipments_supports_all_customers():
    raw_lot_id, _, _ = _shipped_raw_lot()
    rows = traceability.raw_material_to_shipments(
        raw_lot_id, "1900-01-01", "2999-12-31", None
    )
    assert not rows.empty
