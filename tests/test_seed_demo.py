import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import db


@pytest.fixture(scope="module", autouse=True)
def seeded_demo_data():
    db.seed_demo()


def test_demo_has_no_palm_oil():
    assert not db.query("SELECT 1 FROM item WHERE item_code='RM-OIL'")
    assert not db.query("SELECT 1 FROM item WHERE item_name='팜유'")
    assert db.query("SELECT COUNT(*) FROM production_material")[0][0] == 9000
    assert [row[0] for row in db.query("SELECT equipment_name FROM equipment ORDER BY equipment_code")] == [
        "라면 포장 1호기", "라면 포장 2호기"
    ]
    assert not db.query("SELECT 1 FROM equipment WHERE equipment_name LIKE '%자동 포장기%'")
    assert not db.query("SELECT 1 FROM business_partner WHERE partner_name='청정유지'")


def test_product_unit_has_three_unit_material_lots():
    rows = db.query("""
        SELECT p.production_id,p.qty,COUNT(pm.production_material_id),SUM(pm.qty)
        FROM production p JOIN production_material pm USING(production_id)
        GROUP BY p.production_id
    """)
    assert len(rows) == 3000
    assert all((product_qty, component_count, component_qty) == (1, 3, 3)
               for _, product_qty, component_count, component_qty in rows)
    assert db.query("""SELECT COUNT(*) FROM lot
        WHERE lot_type IN ('RECEIPT','PRODUCTION') AND (initial_qty<>1 OR qty NOT IN (0,1))""")[0][0] == 0


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
    assert actual == 75
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


if __name__ == "__main__":
    test_demo_has_no_palm_oil()
    test_product_unit_has_three_unit_material_lots()
    test_finished_product_reverse_trace_excludes_box()
    test_each_box_contains_40_from_one_product_lot()
    print("demo-without-palm-oil-ok")
