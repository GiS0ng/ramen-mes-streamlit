import sys
from datetime import date
from pathlib import Path

import pytest


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import db
from repositories import production_quality as quality_repository
from services import production


@pytest.fixture(scope="module", autouse=True)
def seeded_production_data():
    db.seed_demo()


def test_production_request_schema_supports_equipment():
    columns = {row[1] for row in db.query("PRAGMA table_info(production_request)")}
    assert "equipment_id" in columns
    equipment_columns = {row[1] for row in db.query("PRAGMA table_info(equipment)")}
    assert "capacity_per_minute" in equipment_columns


def test_create_production_plan_with_equipment_product_and_quantity():
    equipment_id = db.query(
        "SELECT equipment_id FROM equipment ORDER BY equipment_id LIMIT 1"
    )[0][0]
    product_id = db.query(
        "SELECT item_id FROM item WHERE item_type='PRODUCT' ORDER BY item_id LIMIT 1"
    )[0][0]

    plan_id = production.create_plan(equipment_id, product_id, 250)
    plan = db.query(
        """SELECT equipment_id,item_id,requested_qty,request_date,status
           FROM production_request WHERE production_request_id=?""",
        (plan_id,),
    )[0]
    assert tuple(plan) == (
        equipment_id, product_id, 250, date.today().isoformat(), "PLANNED"
    )
    plans = quality_repository.production_plans()
    assert plan_id in [
        row[0] for row in db.query(
            "SELECT production_request_id FROM production_request WHERE status='PLANNED'"
        )
    ]
    assert not plans.empty
    created_plan = plans[plans["생산수량"] == 250].iloc[0]
    assert created_plan["분당생산능력"] == 1
    assert created_plan["예상포장시간_분"] == 250


def test_defect_lot_lookup_filters_by_equipment_and_production_date():
    target = db.query(
        """SELECT p.production_id,p.equipment_id,p.production_date,p.output_lot_id
           FROM production p
           WHERE p.status='COMPLETED'
             AND NOT EXISTS(
                 SELECT 1 FROM production_defect pd
                 WHERE pd.production_id=p.production_id
             )
           ORDER BY p.production_id LIMIT 1"""
    )[0]
    production_id, equipment_id, production_date, _ = target

    assert production_date in quality_repository.production_dates(equipment_id)
    lot_options = quality_repository.production_lot_options(
        equipment_id, production_date
    )
    assert production_id in lot_options.values()

    defect_code_id = db.query(
        "SELECT defect_code_id FROM defect_code ORDER BY defect_code_id LIMIT 1"
    )[0][0]
    production.register_defect(
        production_id, defect_code_id, 1, date.today().isoformat(), "조회 기반 등록"
    )
    defective = quality_repository.defective_products()
    assert not defective.empty
    assert (
        (defective["불량설비"].notna())
        & (defective["생산일"] == production_date)
        & (defective["불량수량"] == 1)
    ).any()
