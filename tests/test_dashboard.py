import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import db


@pytest.fixture(scope="module", autouse=True)
def seeded_dashboard_data():
    db.seed_demo()


def test_equipment_yield_is_valid():
    frame = db.dataframe("""
        SELECT COALESCE(e.equipment_name, '미지정 설비') 설비,
               ROUND(SUM(p.qty), 2) 총생산량,
               ROUND(SUM(COALESCE(d.defect_qty, 0)), 2) 불량량,
               ROUND(SUM(p.qty) - SUM(COALESCE(d.defect_qty, 0)), 2) 양품량,
               ROUND((SUM(p.qty) - SUM(COALESCE(d.defect_qty, 0))) * 100.0
                     / NULLIF(SUM(p.qty), 0), 2) 수율
        FROM production p
        LEFT JOIN equipment e ON e.equipment_id = p.equipment_id
        LEFT JOIN (
            SELECT production_id, SUM(defect_qty) defect_qty
            FROM production_defect GROUP BY production_id
        ) d ON d.production_id = p.production_id
        WHERE p.status = 'COMPLETED'
        GROUP BY p.equipment_id, e.equipment_name
    """)
    assert not frame.empty
    assert frame["수율"].between(0, 100).all()
    assert (frame["양품량"] + frame["불량량"] == frame["총생산량"]).all()


def test_finished_goods_stock_is_non_negative():
    stock = db.query(
        "SELECT COALESCE(SUM(qty), 0) FROM lot WHERE lot_type='PRODUCTION'"
    )[0][0]
    assert stock >= 0


def test_equipment_defect_code_counts_are_available():
    frame = db.dataframe("""
        SELECT e.equipment_name 설비,dc.defect_code 불량코드,
               COUNT(pd.production_defect_id) 발생횟수
        FROM production_defect pd JOIN production p USING(production_id)
        JOIN equipment e USING(equipment_id) JOIN defect_code dc USING(defect_code_id)
        GROUP BY e.equipment_id,dc.defect_code_id
    """)
    assert not frame.empty
    assert (frame["발생횟수"] > 0).all()


def test_material_alert_is_aggregated_by_item():
    frame = db.dataframe("""
        SELECT i.item_code,COALESCE(SUM(l.qty),0) total_qty,i.safety_stock
        FROM item i LEFT JOIN lot l
          ON l.item_id=i.item_id AND l.lot_type='RECEIPT'
        WHERE i.item_type='MATERIAL' GROUP BY i.item_id
    """)
    material_count = db.query("SELECT COUNT(*) FROM item WHERE item_type='MATERIAL'")[0][0]
    assert len(frame) == material_count
    components = frame[frame["item_code"].isin(["RM-NOODLE", "RM-SOUP", "RM-PACK"])]
    assert len(components) == 3
    assert (components["safety_stock"] == 500).all()


if __name__ == "__main__":
    test_equipment_yield_is_valid()
    test_finished_goods_stock_is_non_negative()
    test_equipment_defect_code_counts_are_available()
    test_material_alert_is_aggregated_by_item()
    print("dashboard-chart-data-ok")
