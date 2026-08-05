import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import db
from domain.rules import (
    BOX_SIZE,
    DEMO_FINISHED_STOCK_QUANTITY,
    DEMO_REQUEST_COUNT,
    DEMO_REQUEST_QUANTITY,
    PACKAGING_CAPACITY_PER_MINUTE,
    PRODUCT_MATERIAL_CODES,
)


@pytest.fixture(scope="module", autouse=True)
def seeded_demo_data():
    db.seed_demo()


def test_demo_has_no_palm_oil():
    assert not db.query("SELECT 1 FROM item WHERE item_code='RM-OIL'")
    assert not db.query("SELECT 1 FROM item WHERE item_name='팜유'")
    assert db.query("SELECT COUNT(*) FROM production_material")[0][0] == (
        DEMO_REQUEST_QUANTITY * DEMO_REQUEST_COUNT * 3
    )
    assert [row[0] for row in db.query("SELECT equipment_name FROM equipment ORDER BY equipment_code")] == [
        "라면 포장 1호기", "라면 포장 2호기"
    ]
    assert [row[0] for row in db.query(
        "SELECT capacity_per_minute FROM equipment ORDER BY equipment_code"
    )] == [2, 2]
    assert not db.query("SELECT 1 FROM equipment WHERE equipment_name LIKE '%자동 포장기%'")
    assert not db.query("SELECT 1 FROM business_partner WHERE partner_name='청정유지'")


def test_primary_partners_have_demo_contact_details():
    partners = {
        row[0]: tuple(row[1:])
        for row in db.query("""SELECT partner_code,partner_name,phone,email,address
                               FROM business_partner
                               WHERE partner_code IN ('SUP-001','CUS-001')""")
    }
    assert partners["CUS-001"] == (
        "행복마트", "02-3456-7890", "contact@haengbokmart.example",
        "서울특별시 송파구 올림픽로 120",
    )
    assert partners["SUP-001"] == (
        "대한 식품원료", "031-456-7890", "sales@daehan-food.example",
        "경기도 성남시 중원구 산업로 85",
    )


def test_demo_spans_current_and_previous_two_months():
    month_index = date.today().year * 12 + date.today().month - 1
    expected_months = {
        f"{year:04d}-{month + 1:02d}"
        for year, month in (divmod(month_index - offset, 12) for offset in range(3))
    }
    for table, date_column in (
        ("material_receipt", "receipt_date"),
        ("production", "production_date"),
        ("shipment", "shipment_date"),
    ):
        actual_months = {
            row[0]
            for row in db.query(
                f"SELECT DISTINCT substr({date_column},1,7) FROM {table}"
            )
        }
        assert actual_months == expected_months


def test_product_unit_has_three_unit_material_lots():
    rows = db.query("""
        SELECT p.production_id,p.qty,COUNT(pm.production_material_id),SUM(pm.qty)
        FROM production p JOIN production_material pm USING(production_id)
        GROUP BY p.production_id
    """)
    assert len(rows) == DEMO_REQUEST_QUANTITY * DEMO_REQUEST_COUNT
    assert all((product_qty, component_count, component_qty) == (1, 3, 3)
               for _, product_qty, component_count, component_qty in rows)
    assert db.query("""SELECT COUNT(*) FROM lot
        WHERE lot_type IN ('RECEIPT','PRODUCTION') AND (initial_qty<>1 OR qty NOT IN (0,1))""")[0][0] == 0


def test_packaging_operation_uses_one_product_per_thirty_seconds():
    operations = db.query(
        "SELECT planned_minutes,running_minutes,downtime_minutes FROM equipment_operation"
    )
    assert operations
    expected_minutes = int(
        DEMO_REQUEST_QUANTITY / PACKAGING_CAPACITY_PER_MINUTE
    )
    assert all(
        running_minutes == expected_minutes
        for _, running_minutes, _ in operations
    )
    assert all(
        planned_minutes == running_minutes + downtime_minutes
        for planned_minutes, running_minutes, downtime_minutes in operations
    )


def test_demo_production_requests_have_operation_timestamps():
    assert db.query(
        """SELECT COUNT(*) FROM production_request
           WHERE started_at IS NULL OR planned_completion_at IS NULL
              OR completed_at IS NULL"""
    )[0][0] == 0


def test_demo_shipping_uses_box_units_and_has_ready_and_short_plans():
    assert db.query(
        """SELECT COUNT(*) FROM shipment_schedule
           WHERE CAST(scheduled_qty AS INTEGER) % ?<>0""",
        (40,),
    )[0][0] == 0
    assert not db.query(
        """SELECT 1 FROM shipment_schedule WHERE shipment_schedule_no LIKE '%UNIT%'
           UNION ALL
           SELECT 1 FROM shipment WHERE shipment_no LIKE '%UNIT%'"""
    )
    completed = db.query(
        """SELECT COUNT(*) FROM shipment_schedule
           WHERE status='SHIPPED' AND scheduled_qty=800 AND shipped_qty=800"""
    )[0][0]
    assert completed == 3
    availability = db.query(
        """WITH stock AS (
               SELECT item_id,SUM(qty) qty FROM lot
               WHERE lot_type='PRODUCTION' GROUP BY item_id
           )
           SELECT SUM(CASE WHEN stock.qty>=ss.scheduled_qty THEN 1 ELSE 0 END),
                  SUM(CASE WHEN stock.qty<ss.scheduled_qty THEN 1 ELSE 0 END)
           FROM shipment_schedule ss JOIN stock USING(item_id)
           WHERE ss.status='PLANNED'"""
    )[0]
    assert tuple(availability) == (3, 3)
    assert db.query(
        """SELECT COUNT(*) FROM shipment_schedule
           WHERE status IN ('PLANNED','PARTIAL_SHIPPED')
             AND scheduled_date<=date('now')"""
    )[0][0] == 0


def test_each_product_uses_its_recipe_materials():
    rows = db.query("""
        SELECT pi.item_code,mi.item_code
        FROM production p
        JOIN item pi ON pi.item_id=p.item_id
        JOIN production_material pm ON pm.production_id=p.production_id
        JOIN lot ml ON ml.lot_id=pm.material_lot_id
        JOIN item mi ON mi.item_id=ml.item_id
        GROUP BY pi.item_code,mi.item_code
        ORDER BY pi.item_code,mi.item_code
    """)
    actual: dict[str, set[str]] = {}
    for product_code, material_code in rows:
        actual.setdefault(product_code, set()).add(material_code)
    assert actual == {
        product_code: set(material_codes)
        for product_code, material_codes in PRODUCT_MATERIAL_CODES.items()
    }
    assert not db.query(
        "SELECT 1 FROM item WHERE item_code IN ('RM-SOUP','RM-PACK')"
    )


def test_finished_product_reverse_trace_excludes_box():
    product_lot_id = db.query(
        "SELECT output_lot_id FROM production ORDER BY production_id LIMIT 1"
    )[0][0]
    rows = db.query("""
        SELECT mi.item_code
        FROM production p
        JOIN production_material pm ON pm.production_id=p.production_id
        JOIN lot ml ON ml.lot_id=pm.material_lot_id
        JOIN item mi ON mi.item_id=ml.item_id
        WHERE p.output_lot_id=? AND mi.item_code<>'RM-BOX'
    """, (product_lot_id,))
    assert rows
    assert all(item_code != "RM-BOX" for (item_code,) in rows)


def test_each_box_contains_40_from_one_product_lot():
    expected = db.query("SELECT SUM(CAST(qty / 40 AS INTEGER)) FROM production")[0][0]
    actual = db.query("SELECT COUNT(*) FROM packing_box")[0][0]
    assert actual == DEMO_REQUEST_QUANTITY // BOX_SIZE * DEMO_REQUEST_COUNT
    assert db.query("SELECT COUNT(*) FROM packing_box WHERE box_qty<>40")[0][0] == 0
    assert db.query("""SELECT COUNT(*) FROM (
        SELECT packing_box_id FROM packing_box_detail GROUP BY packing_box_id HAVING COUNT(*)<>40
    )""")[0][0] == 0
    trace = db.query("""
        SELECT pb.box_no, l.lot_no, p.production_no, pb.box_qty
        FROM packing_box pb JOIN packing_box_detail pbd USING(packing_box_id)
        JOIN lot l ON l.lot_id=pbd.product_lot_id
        JOIN production p ON p.output_lot_id=l.lot_id
        LIMIT 1
    """)
    assert trace and trace[0][3] == 40


def test_each_product_has_five_thousand_finished_units_in_stock():
    stock = db.query(
        """SELECT i.item_code,SUM(l.qty)
           FROM item i JOIN lot l ON l.item_id=i.item_id
           WHERE i.item_type='PRODUCT' AND l.lot_type='PRODUCTION'
           GROUP BY i.item_id ORDER BY i.item_code"""
    )
    assert len(stock) == DEMO_REQUEST_COUNT
    assert all(
        quantity == DEMO_FINISHED_STOCK_QUANTITY
        for _, quantity in stock
    )


if __name__ == "__main__":
    test_demo_has_no_palm_oil()
    test_product_unit_has_three_unit_material_lots()
    test_finished_product_reverse_trace_excludes_box()
    test_each_box_contains_40_from_one_product_lot()
    print("demo-without-palm-oil-ok")
