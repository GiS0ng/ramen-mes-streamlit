import sys
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import db
from domain.rules import PRODUCT_MATERIAL_CODES
from repositories import equipment as equipment_repository
from repositories import production_quality as quality_repository
from services import production


@pytest.fixture(scope="module", autouse=True)
def seeded_production_data():
    db.seed_demo()


def test_production_request_schema_supports_equipment():
    columns = {row[1] for row in db.query("PRAGMA table_info(production_request)")}
    assert "equipment_id" in columns
    assert {"started_at", "planned_completion_at", "completed_at"} <= columns
    equipment_columns = {row[1] for row in db.query("PRAGMA table_info(equipment)")}
    assert "capacity_per_minute" in equipment_columns
    assert db.query("PRAGMA user_version")[0][0] == db.SCHEMA_MIGRATION_VERSION


def test_legacy_schema_adds_capacity_before_running_plan_migration():
    connection = sqlite3.connect(":memory:")
    connection.execute(
        """CREATE TABLE equipment(
               equipment_id INTEGER PRIMARY KEY,
               equipment_code TEXT,
               status TEXT
           )"""
    )
    connection.execute(
        """CREATE TABLE production_request(
               production_request_id INTEGER PRIMARY KEY,
               equipment_id INTEGER,
               requested_qty INTEGER,
               status TEXT,
               created_at TEXT
           )"""
    )
    connection.execute(
        "CREATE TABLE shipment_detail(shipment_id INTEGER,product_lot_id INTEGER)"
    )
    connection.execute(
        "CREATE TABLE packing_box_detail(packing_box_id INTEGER,product_lot_id INTEGER)"
    )

    db._migrate_schema(connection)

    equipment_columns = {
        row[1] for row in connection.execute("PRAGMA table_info(equipment)")
    }
    assert "capacity_per_minute" in equipment_columns
    assert connection.execute("PRAGMA user_version").fetchone()[0] == (
        db.SCHEMA_MIGRATION_VERSION
    )
    connection.close()


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
    assert created_plan["분당생산능력"] == 2
    assert created_plan["예상포장시간_분"] == 125


def test_saved_plan_controls_equipment_and_creates_results():
    equipment_id = db.query(
        "SELECT equipment_id FROM equipment ORDER BY equipment_id LIMIT 1"
    )[0][0]
    product_id, product_code = db.query(
        """SELECT item_id,item_code FROM item
           WHERE item_code='FG-MILD'"""
    )[0]
    quantity = 40

    with db.transaction() as connection:
        for material_code in PRODUCT_MATERIAL_CODES[product_code]:
            material_id = connection.execute(
                "SELECT item_id FROM item WHERE item_code=?", (material_code,)
            ).fetchone()[0]
            for serial in range(1, quantity + 1):
                connection.execute(
                    """INSERT INTO lot(
                           lot_no,item_id,lot_type,initial_qty,qty,received_date
                       ) VALUES(?,?, 'RECEIPT',1,1,?)""",
                    (
                        f"TEST-{material_code}-{serial:03d}", material_id,
                        date.today().isoformat(),
                    ),
                )

    plan_id = production.create_plan(equipment_id, product_id, quantity)
    production.start_plan(plan_id)
    assert db.query(
        "SELECT status FROM production_request WHERE production_request_id=?",
        (plan_id,),
    )[0][0] == "IN_PROGRESS"
    assert db.query(
        "SELECT status FROM equipment WHERE equipment_id=?", (equipment_id,)
    )[0][0] == "RUNNING"
    running_plans = equipment_repository.plans("IN_PROGRESS")
    running_plan = running_plans[
        running_plans["계획수량"] == quantity
    ].iloc[-1]
    assert running_plan["가동시작일시"]
    assert running_plan["가동완료계획일시"]
    status_frame = equipment_repository.equipment_status()
    assert "가동 중" in status_frame["설비상태"].tolist()

    completed_quantity = production.complete_plan(
        plan_id, date.today().isoformat(), 5, "테스트 정지"
    )
    assert completed_quantity == quantity
    assert db.query(
        "SELECT status FROM production_request WHERE production_request_id=?",
        (plan_id,),
    )[0][0] == "COMPLETED"
    assert db.query(
        "SELECT status FROM equipment WHERE equipment_id=?", (equipment_id,)
    )[0][0] == "AVAILABLE"
    assert db.query(
        """SELECT COUNT(*) FROM production_request_unit
           WHERE production_request_id=?""",
        (plan_id,),
    )[0][0] == quantity
    assert db.query(
        """SELECT COUNT(*) FROM production_material pm
           JOIN production_request_unit pru USING(production_id)
           WHERE pru.production_request_id=?""",
        (plan_id,),
    )[0][0] == quantity * 3
    assert db.query(
        "SELECT COUNT(*) FROM packing_box WHERE box_no LIKE ?",
        (f"BOX-PLAN-%",),
    )[0][0] >= 1
    operation = db.query(
        """SELECT running_minutes,downtime_minutes,planned_minutes
           FROM equipment_operation
           ORDER BY equipment_operation_id DESC LIMIT 1"""
    )[0]
    assert tuple(operation) == (20, 5, 25)
    assert not equipment_repository.operation_history().empty


def test_running_plan_is_completed_automatically_after_expected_minutes():
    equipment_id = db.query(
        "SELECT equipment_id FROM equipment WHERE status='AVAILABLE' ORDER BY equipment_id LIMIT 1"
    )[0][0]
    product_id, product_code = db.query(
        "SELECT item_id,item_code FROM item WHERE item_code='FG-RAMEN'"
    )[0]
    quantity = 2

    with db.transaction() as connection:
        for material_code in PRODUCT_MATERIAL_CODES[product_code]:
            material_id = connection.execute(
                "SELECT item_id FROM item WHERE item_code=?", (material_code,)
            ).fetchone()[0]
            for serial in range(quantity):
                connection.execute(
                    """INSERT INTO lot(
                           lot_no,item_id,lot_type,initial_qty,qty,received_date
                       ) VALUES(?,?, 'RECEIPT',1,1,?)""",
                    (
                        f"AUTO-{material_code}-{serial}-{datetime.now().timestamp()}",
                        material_id,
                        date.today().isoformat(),
                    ),
                )

    plan_id = production.create_plan(equipment_id, product_id, quantity)
    started_at = datetime(2026, 8, 5, 9, 0, 0)
    production.start_plan(plan_id, started_at=started_at)
    plan = db.query(
        """SELECT status,started_at,planned_completion_at
           FROM production_request WHERE production_request_id=?""",
        (plan_id,),
    )[0]
    assert tuple(plan) == (
        "IN_PROGRESS",
        started_at.isoformat(timespec="seconds"),
        (started_at + timedelta(minutes=1)).isoformat(timespec="seconds"),
    )

    assert production.auto_complete_due_plans(
        started_at + timedelta(seconds=30)
    ) == []
    assert db.query(
        """SELECT COUNT(*) FROM production_request_unit
           WHERE production_request_id=?""",
        (plan_id,),
    )[0][0] == 1
    progress = equipment_repository.plans("IN_PROGRESS")
    progress = progress[progress["계획번호"].str.contains(str(plan_id).zfill(4))].iloc[0]
    assert progress["생산완료수량"] == 1
    assert progress["잔여계획수량"] == 1
    assert db.query(
        """SELECT SUM(l.qty)
           FROM production_request_unit pru
           JOIN production p USING(production_id)
           JOIN lot l ON l.lot_id=p.output_lot_id
           WHERE pru.production_request_id=?""",
        (plan_id,),
    )[0][0] == 1
    assert production.auto_complete_due_plans(
        started_at + timedelta(minutes=1)
    ) == [plan_id]
    status, completed_at = db.query(
        """SELECT status,completed_at FROM production_request
           WHERE production_request_id=?""",
        (plan_id,),
    )[0]
    assert status == "COMPLETED"
    assert completed_at == (started_at + timedelta(minutes=1)).isoformat(
        timespec="seconds"
    )
    assert db.query(
        """SELECT COUNT(*) FROM production_request_unit
           WHERE production_request_id=?""",
        (plan_id,),
    )[0][0] == quantity


def test_single_unit_plan_completes_after_thirty_seconds(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "thirty-seconds.db")
    db.initialize()
    product_id, product_code = db.query(
        "SELECT item_id,item_code FROM item WHERE item_code='FG-RAMEN'"
    )[0]
    equipment_id = db.query(
        "SELECT equipment_id FROM equipment WHERE equipment_code='EQ-PACK-01'"
    )[0][0]
    with db.transaction() as connection:
        for material_code in PRODUCT_MATERIAL_CODES[product_code]:
            material_id = connection.execute(
                "SELECT item_id FROM item WHERE item_code=?", (material_code,)
            ).fetchone()[0]
            connection.execute(
                """INSERT INTO lot(
                       lot_no,item_id,lot_type,initial_qty,qty,received_date
                   ) VALUES(?,?, 'RECEIPT',1,1,?)""",
                (f"THIRTY-{material_code}", material_id, date.today().isoformat()),
            )

    plan_id = production.create_plan(equipment_id, product_id, 1)
    started_at = datetime(2026, 8, 5, 9, 0, 0)
    production.start_plan(plan_id, started_at=started_at)
    planned_completion_at = db.query(
        """SELECT planned_completion_at FROM production_request
           WHERE production_request_id=?""",
        (plan_id,),
    )[0][0]
    assert planned_completion_at == (
        started_at + timedelta(seconds=30)
    ).isoformat(timespec="seconds")
    assert production.auto_complete_due_plans(
        started_at + timedelta(seconds=29)
    ) == []
    assert production.auto_complete_due_plans(
        started_at + timedelta(seconds=30)
    ) == [plan_id]


def test_start_plan_reserves_material_for_its_equipment(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "reservations.db")
    db.initialize()
    product_id, product_code = db.query(
        "SELECT item_id,item_code FROM item WHERE item_code='FG-RAMEN'"
    )[0]
    with db.transaction() as connection:
        for material_code in PRODUCT_MATERIAL_CODES[product_code]:
            material_id = connection.execute(
                "SELECT item_id FROM item WHERE item_code=?", (material_code,)
            ).fetchone()[0]
            connection.execute(
                """INSERT INTO lot(
                       lot_no,item_id,lot_type,initial_qty,qty,received_date
                   ) VALUES(?,?, 'RECEIPT',1,1,?)""",
                (f"RESERVE-{material_code}", material_id, date.today().isoformat()),
            )
        connection.execute(
            """INSERT INTO equipment(
                   equipment_code,equipment_name,equipment_type,location,
                   capacity_per_minute
               ) VALUES('EQ-PACK-02','라면 포장 2호기','포장설비','1공장',2)"""
        )

    equipment_ids = [
        int(row[0])
        for row in db.query("SELECT equipment_id FROM equipment ORDER BY equipment_id")
    ]
    first_plan_id = production.create_plan(equipment_ids[0], product_id, 1)
    second_plan_id = production.create_plan(equipment_ids[1], product_id, 1)
    production.start_plan(first_plan_id)

    assert db.query(
        """SELECT COUNT(*) FROM production_material_reservation
           WHERE production_request_id=?""",
        (first_plan_id,),
    )[0][0] == 3
    with pytest.raises(ValueError, match="예약 가능한 낱개 LOT 재고"):
        production.start_plan(second_plan_id)
    assert db.query(
        "SELECT status FROM production_request WHERE production_request_id=?",
        (second_plan_id,),
    )[0][0] == "PLANNED"


def test_running_plan_errors_do_not_block_later_plans(monkeypatch):
    started_at = datetime(2026, 8, 5, 9, 0, 0)
    now = started_at + timedelta(minutes=1)
    monkeypatch.setattr(
        production.db,
        "query",
        lambda *args, **kwargs: [
            (101, started_at.isoformat(), now.isoformat(), 2, 2),
            (102, started_at.isoformat(), now.isoformat(), 2, 2),
        ],
    )
    processed: list[int] = []

    def fake_advance(plan_id, target_quantity, production_date):
        processed.append(plan_id)
        if plan_id == 101:
            raise ValueError("원재료 부족")
        return target_quantity

    monkeypatch.setattr(production, "_advance_plan", fake_advance)
    failures: dict[int, str] = {}
    created = production.advance_running_plans(now, failures=failures)

    assert processed == [101, 102]
    assert created == {102: 2}
    assert failures == {101: "원재료 부족"}


def test_access_catch_up_tolerates_concurrent_completion(monkeypatch):
    planned_completion_at = datetime(2026, 8, 5, 9, 0, 30)
    query_results = iter(
        [
            [(501, planned_completion_at.isoformat())],
            [("COMPLETED",)],
        ]
    )
    monkeypatch.setattr(
        production,
        "advance_running_plans",
        lambda now, failures: {},
    )
    monkeypatch.setattr(
        production.db,
        "query",
        lambda *args, **kwargs: next(query_results),
    )
    monkeypatch.setattr(
        production,
        "complete_plan",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            ValueError("다른 접속에서 이미 완료됨")
        ),
    )

    assert production.auto_complete_due_plans(planned_completion_at) == []


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
