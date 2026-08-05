from __future__ import annotations

from datetime import date, datetime, timedelta
from math import ceil, floor
from zoneinfo import ZoneInfo

import db
from domain.rules import BOX_SIZE, PRODUCT_MATERIAL_CODES


KOREA_TIMEZONE = ZoneInfo("Asia/Seoul")


def _now() -> datetime:
    return datetime.now(KOREA_TIMEZONE).replace(tzinfo=None)


def create_plan(equipment_id: int, product_id: int, quantity: int) -> int:
    """설비·제품·수량을 기준으로 생산 계획서를 등록한다."""
    if quantity <= 0:
        raise ValueError("생산수량은 1개 이상이어야 합니다.")

    with db.transaction() as connection:
        equipment = connection.execute(
            "SELECT 1 FROM equipment WHERE equipment_id=? AND is_active='Y'",
            (equipment_id,),
        ).fetchone()
        product = connection.execute(
            "SELECT 1 FROM item WHERE item_id=? AND item_type='PRODUCT' AND is_active='Y'",
            (product_id,),
        ).fetchone()
        if equipment is None:
            raise ValueError("사용 가능한 설비를 선택해 주세요.")
        if product is None:
            raise ValueError("사용 가능한 완제품 품목을 선택해 주세요.")

        today = date.today()
        next_id = connection.execute(
            "SELECT COALESCE(MAX(production_request_id),0)+1 FROM production_request"
        ).fetchone()[0]
        request_no = f"PLAN-{today:%Y%m%d}-{next_id:04d}"
        cursor = connection.execute(
            """INSERT INTO production_request(
                   request_no,item_id,equipment_id,requested_qty,request_date,status
               ) VALUES(?,?,?,?,?, 'PLANNED')""",
            (request_no, product_id, equipment_id, quantity, today.isoformat()),
        )
        return int(cursor.lastrowid)


def start_plan(plan_id: int, started_at: datetime | None = None) -> int:
    """저장된 생산계획을 시작하고 지정 설비를 가동 상태로 변경한다."""
    with db.transaction() as connection:
        plan = connection.execute(
            """SELECT pr.item_id,pr.equipment_id,pr.requested_qty,
                      e.status,e.capacity_per_minute
               FROM production_request pr
               JOIN equipment e ON e.equipment_id=pr.equipment_id
               WHERE pr.production_request_id=? AND pr.status='PLANNED'""",
            (plan_id,),
        ).fetchone()
        if plan is None:
            raise ValueError("가동 가능한 생산계획서를 찾을 수 없습니다.")
        if plan[3] != "AVAILABLE":
            raise ValueError("선택한 설비가 현재 가동 가능한 상태가 아닙니다.")

        _available_material_lots(connection, plan[0], int(plan[2]))
        started_at = started_at or _now()
        running_minutes = ceil(int(plan[2]) / float(plan[4]))
        planned_completion_at = started_at + timedelta(minutes=running_minutes)
        connection.execute(
            """UPDATE production_request
               SET status='IN_PROGRESS',started_at=?,planned_completion_at=?
               WHERE production_request_id=?""",
            (
                started_at.isoformat(timespec="seconds"),
                planned_completion_at.isoformat(timespec="seconds"),
                plan_id,
            ),
        )
        connection.execute(
            "UPDATE equipment SET status='RUNNING' WHERE equipment_id=?",
            (plan[1],),
        )
        return int(plan[1])


def auto_complete_due_plans(now: datetime | None = None) -> list[int]:
    """예상 가동시간이 지난 생산계획을 실적과 함께 자동 완료한다."""
    now = now or _now()
    advance_running_plans(now)
    due_plans = db.query(
        """SELECT production_request_id,planned_completion_at
           FROM production_request
           WHERE status='IN_PROGRESS'
             AND planned_completion_at IS NOT NULL
             AND planned_completion_at<=?
           ORDER BY planned_completion_at,production_request_id""",
        (now.isoformat(timespec="seconds"),),
    )
    completed: list[int] = []
    for plan_id, planned_completion_at in due_plans:
        effective_completion = datetime.fromisoformat(planned_completion_at)
        complete_plan(
            int(plan_id),
            effective_completion.date().isoformat(),
            0,
            "가동시간 기준 자동 완료",
            completed_at=effective_completion,
        )
        completed.append(int(plan_id))
    return completed


def advance_running_plans(now: datetime | None = None) -> dict[int, int]:
    """경과 가동시간만큼 완제품을 낱개 생성하고 계획 잔량을 감소시킨다."""
    now = now or _now()
    running_plans = db.query(
        """SELECT pr.production_request_id,pr.started_at,
                  pr.planned_completion_at,pr.requested_qty,
                  e.capacity_per_minute
           FROM production_request pr
           JOIN equipment e ON e.equipment_id=pr.equipment_id
           WHERE pr.status='IN_PROGRESS' AND pr.started_at IS NOT NULL
           ORDER BY pr.production_request_id"""
    )
    created_by_plan: dict[int, int] = {}
    for plan_id, started_at, planned_completion_at, quantity, capacity in running_plans:
        start = datetime.fromisoformat(started_at)
        elapsed_minutes = max(0.0, (now - start).total_seconds() / 60)
        target_quantity = min(
            int(quantity), floor(elapsed_minutes * float(capacity))
        )
        if target_quantity <= 0:
            continue
        effective_time = min(
            now,
            datetime.fromisoformat(planned_completion_at)
            if planned_completion_at else now,
        )
        created = _advance_plan(
            int(plan_id), target_quantity, effective_time.date().isoformat()
        )
        if created:
            created_by_plan[int(plan_id)] = created
    return created_by_plan


def _advance_plan(plan_id: int, target_quantity: int, production_date: str) -> int:
    with db.transaction() as connection:
        plan = connection.execute(
            """SELECT pr.request_no,pr.item_id,pr.equipment_id,pr.requested_qty
               FROM production_request pr
               WHERE pr.production_request_id=? AND pr.status='IN_PROGRESS'""",
            (plan_id,),
        ).fetchone()
        if plan is None:
            return 0
        request_no, product_id, equipment_id, requested_qty = plan
        produced_quantity = int(connection.execute(
            """SELECT COUNT(*) FROM production_request_unit
               WHERE production_request_id=?""",
            (plan_id,),
        ).fetchone()[0])
        target_quantity = min(int(requested_qty), target_quantity)
        create_quantity = target_quantity - produced_quantity
        if create_quantity <= 0:
            return 0

        material_lots = _available_material_lots(
            connection, int(product_id), create_quantity
        )
        _create_production_units(
            connection,
            plan_id,
            str(request_no),
            int(product_id),
            int(equipment_id),
            production_date,
            create_quantity,
            material_lots,
            serial_start=produced_quantity,
        )
        _create_boxes_for_request(
            connection, plan_id, str(request_no), production_date
        )
        return create_quantity


def complete_plan(
    plan_id: int,
    operation_date: str,
    downtime_minutes: int,
    downtime_reason: str,
    completed_at: datetime | None = None,
) -> int:
    """가동 중인 계획을 생산실적·LOT·설비실적으로 완료 처리한다."""
    if downtime_minutes < 0:
        raise ValueError("비가동 시간은 0분 이상이어야 합니다.")

    with db.transaction() as connection:
        plan = connection.execute(
            """SELECT pr.request_no,pr.item_id,pr.equipment_id,pr.requested_qty,
                      e.capacity_per_minute
               FROM production_request pr
               JOIN equipment e ON e.equipment_id=pr.equipment_id
               WHERE pr.production_request_id=? AND pr.status='IN_PROGRESS'
                 AND e.status='RUNNING'""",
            (plan_id,),
        ).fetchone()
        if plan is None:
            raise ValueError("가동 중인 생산계획서를 찾을 수 없습니다.")

        request_no, product_id, equipment_id, quantity, capacity = plan
        produced_quantity = int(connection.execute(
            """SELECT COUNT(*) FROM production_request_unit
               WHERE production_request_id=?""",
            (plan_id,),
        ).fetchone()[0])
        remaining_quantity = int(quantity) - produced_quantity
        if remaining_quantity > 0:
            material_lots = _available_material_lots(
                connection, int(product_id), remaining_quantity
            )
            _create_production_units(
                connection,
                plan_id,
                str(request_no),
                int(product_id),
                int(equipment_id),
                operation_date,
                remaining_quantity,
                material_lots,
                serial_start=produced_quantity,
            )
        _create_boxes_for_request(
            connection, plan_id, str(request_no), operation_date
        )
        first_production_id = int(connection.execute(
            """SELECT production_id FROM production_request_unit
               WHERE production_request_id=?
               ORDER BY production_request_unit_id LIMIT 1""",
            (plan_id,),
        ).fetchone()[0])

        running_minutes = ceil(int(quantity) / float(capacity))
        total_minutes = running_minutes + downtime_minutes
        connection.execute(
            """INSERT INTO equipment_operation(
                   equipment_id,production_id,operation_date,planned_minutes,
                   running_minutes,downtime_minutes,downtime_reason
               ) VALUES(?,?,?,?,?,?,?)""",
            (
                equipment_id, first_production_id, operation_date, total_minutes,
                running_minutes, downtime_minutes, downtime_reason,
            ),
        )
        connection.execute(
            """UPDATE production_request
               SET status='COMPLETED',completed_at=?
               WHERE production_request_id=?""",
            (
                (completed_at or _now()).isoformat(timespec="seconds"),
                plan_id,
            ),
        )
        connection.execute(
            "UPDATE equipment SET status='AVAILABLE' WHERE equipment_id=?",
            (equipment_id,),
        )
        return int(quantity)


def create_request(
    request_no: str,
    product_id: int,
    equipment_id: int | None,
    production_date: str,
    quantity: int,
) -> int:
    """이전 호출 호환성을 위해 생산요청을 즉시 완료 실적으로 전개한다."""
    if quantity <= 0:
        raise ValueError("생산 요청수량은 1개 이상이어야 합니다.")
    if equipment_id is None:
        raise ValueError("생산 설비를 선택해 주세요.")

    with db.transaction() as connection:
        material_lots = _available_material_lots(connection, product_id, quantity)
        request_id = connection.execute(
            """INSERT INTO production_request(
                   request_no,item_id,equipment_id,requested_qty,request_date,status
               ) VALUES(?,?,?,?,?, 'COMPLETED')""",
            (request_no, product_id, equipment_id, quantity, production_date),
        ).lastrowid
        _create_production_units(
            connection,
            int(request_id),
            request_no,
            product_id,
            equipment_id,
            production_date,
            quantity,
            material_lots,
        )
        _create_boxes_for_request(
            connection, int(request_id), request_no, production_date
        )
        return int(request_id)


def _available_material_lots(connection, product_id: int, quantity: int) -> dict[str, list[int]]:
    product = connection.execute(
        "SELECT item_code FROM item WHERE item_id=? AND item_type='PRODUCT'",
        (product_id,),
    ).fetchone()
    if product is None or product[0] not in PRODUCT_MATERIAL_CODES:
        raise ValueError("등록된 제품별 원재료 조합이 없습니다.")

    material_lots: dict[str, list[int]] = {}
    for code in PRODUCT_MATERIAL_CODES[product[0]]:
        rows = connection.execute(
            """SELECT l.lot_id FROM lot l JOIN item i ON i.item_id=l.item_id
               WHERE i.item_code=? AND l.lot_type='RECEIPT' AND l.qty=1
               ORDER BY l.expire_date,l.received_date,l.lot_id LIMIT ?""",
            (code, quantity),
        ).fetchall()
        if len(rows) < quantity:
            raise ValueError(f"{code} 낱개 LOT 재고가 {quantity}개보다 부족합니다.")
        material_lots[code] = [int(row[0]) for row in rows]
    return material_lots


def _create_production_units(
    connection,
    request_id: int,
    request_no: str,
    product_id: int,
    equipment_id: int,
    production_date: str,
    quantity: int,
    material_lots: dict[str, list[int]],
    serial_start: int = 0,
) -> list[int]:
    production_ids: list[int] = []
    for index in range(quantity):
        serial = serial_start + index + 1
        lot_id = connection.execute(
            """INSERT INTO lot(
                   lot_no,item_id,lot_type,initial_qty,qty,produced_date
               ) VALUES(?,?, 'PRODUCTION',1,1,?)""",
            (f"FG-{request_no}-{serial:05d}", product_id, production_date),
        ).lastrowid
        production_id = connection.execute(
            """INSERT INTO production(
                   production_no,item_id,output_lot_id,equipment_id,
                   production_date,qty,status
               ) VALUES(?,?,?,?,?,1,'COMPLETED')""",
            (
                f"PRD-{request_no}-{serial:05d}", product_id, lot_id,
                equipment_id, production_date,
            ),
        ).lastrowid
        connection.execute(
            "INSERT INTO production_request_unit(production_request_id,production_id) VALUES(?,?)",
            (request_id, production_id),
        )
        for code, lots in material_lots.items():
            connection.execute(
                "INSERT INTO production_material(production_id,material_lot_id,qty) VALUES(?,?,1)",
                (production_id, lots[index]),
            )
        production_ids.append(int(production_id))
    return production_ids


def _create_boxes_for_request(
    connection,
    request_id: int,
    request_no: str,
    packed_date: str,
) -> int:
    existing_boxes = int(connection.execute(
        "SELECT COUNT(*) FROM packing_box WHERE box_no LIKE ?",
        (f"BOX-{request_no}-%",),
    ).fetchone()[0])
    unboxed_lots = [
        int(row[0])
        for row in connection.execute(
            """SELECT p.output_lot_id
               FROM production_request_unit pru
               JOIN production p ON p.production_id=pru.production_id
               LEFT JOIN packing_box_detail pbd
                 ON pbd.product_lot_id=p.output_lot_id
               WHERE pru.production_request_id=?
                 AND pbd.packing_box_detail_id IS NULL
               ORDER BY pru.production_request_unit_id""",
            (request_id,),
        ).fetchall()
    ]
    created_boxes = 0
    for offset in range(0, len(unboxed_lots) - BOX_SIZE + 1, BOX_SIZE):
        box_number = existing_boxes + created_boxes + 1
        box_id = connection.execute(
            "INSERT INTO packing_box(box_no,box_qty,packed_date) VALUES(?,?,?)",
            (f"BOX-{request_no}-{box_number:04d}", BOX_SIZE, packed_date),
        ).lastrowid
        connection.executemany(
            "INSERT INTO packing_box_detail(packing_box_id,product_lot_id) VALUES(?,?)",
            [
                (box_id, lot_id)
                for lot_id in unboxed_lots[offset:offset + BOX_SIZE]
            ],
        )
        created_boxes += 1
    return created_boxes


def register_material(production_id: int, material_lot_id: int, quantity: float) -> int:
    return db.execute(
        "INSERT INTO production_material(production_id,material_lot_id,qty) VALUES(?,?,?)",
        (production_id, material_lot_id, quantity),
    )


def register_defect(
    production_id: int,
    defect_code_id: int,
    quantity: float,
    defect_date: str,
    memo: str,
) -> int:
    production = db.query(
        "SELECT 1 FROM production WHERE production_id=? AND status='COMPLETED'",
        (production_id,),
    )
    if not production:
        raise ValueError("완료된 생산 LOT만 불량 등록할 수 있습니다.")
    return db.execute(
        """INSERT INTO production_defect(
               production_id,defect_code_id,defect_qty,defect_date,memo
           ) VALUES(?,?,?,?,?)""",
        (production_id, defect_code_id, quantity, defect_date, memo),
    )
