from __future__ import annotations

import pandas as pd

import db


def plan_options(status: str, available_only: bool = False) -> dict[str, int]:
    availability_filter = "AND e.status='AVAILABLE'" if available_only else ""
    return db.options(
        f"""SELECT pr.production_request_id,
                   pr.request_no||' · '||e.equipment_name||' · '||
                   i.item_name||' · '||pr.requested_qty||'개'
            FROM production_request pr
            JOIN equipment e ON e.equipment_id=pr.equipment_id
            JOIN item i ON i.item_id=pr.item_id
            WHERE pr.status=? {availability_filter}
            ORDER BY pr.request_date,pr.production_request_id""",
        (status,),
    )


def plans(status: str) -> pd.DataFrame:
    return db.dataframe(
        """WITH plan_progress AS (
               SELECT production_request_id,COUNT(*) completed_qty
               FROM production_request_unit
               GROUP BY production_request_id
           )
           SELECT pr.request_no 계획번호,e.equipment_name 설비,
                  i.item_name 품목,pr.requested_qty 계획수량,
                  COALESCE(pp.completed_qty,0) 생산완료수량,
                  pr.requested_qty-COALESCE(pp.completed_qty,0) 잔여계획수량,
                  e.capacity_per_minute 분당생산능력,
                  ROUND(pr.requested_qty/NULLIF(e.capacity_per_minute,0),2) 예상가동시간_분,
                  REPLACE(pr.started_at,'T',' ') 가동시작일시,
                  REPLACE(pr.planned_completion_at,'T',' ') 가동완료계획일시,
                  pr.request_date 계획등록일,pr.status 상태
           FROM production_request pr
           JOIN equipment e ON e.equipment_id=pr.equipment_id
           JOIN item i ON i.item_id=pr.item_id
           LEFT JOIN plan_progress pp
             ON pp.production_request_id=pr.production_request_id
           WHERE pr.status=?
           ORDER BY pr.request_date,pr.production_request_id""",
        (status,),
    )


def equipment_status() -> pd.DataFrame:
    return db.dataframe(
        """SELECT e.equipment_code 설비코드,e.equipment_name 설비명,
                  e.capacity_per_minute 분당생산능력,
                  CASE e.status
                      WHEN 'AVAILABLE' THEN '가동 가능'
                      WHEN 'RUNNING' THEN '가동 중'
                      WHEN 'STOPPED' THEN '정지'
                      WHEN 'MAINTENANCE' THEN '점검 중'
                  END 설비상태,
                  pr.request_no 진행계획,i.item_name 생산품목,
                  pr.requested_qty 계획수량,
                  COALESCE(pp.completed_qty,0) 생산완료수량,
                  pr.requested_qty-COALESCE(pp.completed_qty,0) 잔여계획수량,
                  REPLACE(pr.planned_completion_at,'T',' ') 가동완료계획일시
           FROM equipment e
           LEFT JOIN production_request pr
             ON pr.equipment_id=e.equipment_id AND pr.status='IN_PROGRESS'
           LEFT JOIN item i ON i.item_id=pr.item_id
           LEFT JOIN (
               SELECT production_request_id,COUNT(*) completed_qty
               FROM production_request_unit
               GROUP BY production_request_id
           ) pp ON pp.production_request_id=pr.production_request_id
           WHERE e.is_active='Y'
           ORDER BY e.equipment_code"""
    )


def performance() -> pd.DataFrame:
    return db.dataframe(
        """SELECT e.equipment_code 설비코드,e.equipment_name 설비명,
                  COALESCE(SUM(eo.planned_minutes),0) 계획시간,
                  COALESCE(SUM(eo.running_minutes),0) 가동시간,
                  COALESCE(SUM(eo.downtime_minutes),0) 비가동시간,
                  ROUND(SUM(eo.running_minutes)*100.0/
                        NULLIF(SUM(eo.planned_minutes),0),2) 가동률
           FROM equipment e
           LEFT JOIN equipment_operation eo USING(equipment_id)
           GROUP BY e.equipment_id
           ORDER BY e.equipment_code"""
    )


def operation_history() -> pd.DataFrame:
    return db.dataframe(
        """SELECT eo.operation_date 가동일,e.equipment_name 설비,
                  pr.request_no 계획번호,i.item_name 생산품목,
                  pr.requested_qty 생산수량,eo.running_minutes 가동시간,
                  eo.downtime_minutes 비가동시간,
                  eo.planned_minutes 총소요시간,eo.downtime_reason 비가동사유
           FROM equipment_operation eo
           JOIN equipment e ON e.equipment_id=eo.equipment_id
           LEFT JOIN production_request_unit pru
             ON pru.production_id=eo.production_id
           LEFT JOIN production_request pr
             ON pr.production_request_id=pru.production_request_id
           LEFT JOIN item i ON i.item_id=pr.item_id
           ORDER BY eo.operation_date DESC,eo.equipment_operation_id DESC"""
    )


def worker_heartbeat() -> pd.DataFrame:
    return db.dataframe(
        """SELECT worker_name Worker,
                  REPLACE(last_run_at,'T',' ') 마지막실행일시,
                  CASE status
                      WHEN 'RUNNING' THEN '정상 실행 중'
                      WHEN 'ERROR' THEN '오류'
                      WHEN 'STOPPED' THEN '중지'
                  END 상태,
                  message 최근처리결과
           FROM worker_heartbeat
           WHERE worker_name='production'"""
    )
