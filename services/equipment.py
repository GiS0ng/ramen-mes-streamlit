from __future__ import annotations

import db


def register_operation(
    equipment_id: int,
    production_id: int | None,
    operation_date: str,
    planned_minutes: int,
    running_minutes: int,
    downtime_minutes: int,
    reason: str,
) -> int:
    return db.execute(
        """INSERT INTO equipment_operation(
               equipment_id,production_id,operation_date,planned_minutes,
               running_minutes,downtime_minutes,downtime_reason
           ) VALUES(?,?,?,?,?,?,?)""",
        (equipment_id, production_id, operation_date, planned_minutes, running_minutes, downtime_minutes, reason),
    )
