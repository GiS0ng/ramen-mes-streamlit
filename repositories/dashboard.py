from __future__ import annotations

import pandas as pd

import db


def summary_metrics():
    return db.query(
        """SELECT
        (SELECT COUNT(*) FROM production WHERE production_date=date('now')),
        (SELECT COALESCE(SUM(qty),0) FROM production WHERE production_date=date('now')),
        (SELECT COALESCE(SUM(defect_qty),0) FROM production_defect WHERE defect_date=date('now')),
        (SELECT COALESCE(SUM(shipment_qty),0) FROM shipment_detail sd JOIN shipment s USING(shipment_id) WHERE s.shipment_date=date('now')),
        (SELECT COALESCE(SUM(qty),0) FROM lot WHERE lot_type='PRODUCTION'),
        (SELECT COUNT(*) FROM (
            SELECT i.item_id FROM item i LEFT JOIN lot l
              ON l.item_id=i.item_id AND l.lot_type='RECEIPT'
            WHERE i.item_type='MATERIAL' AND i.is_active='Y'
            GROUP BY i.item_id HAVING COALESCE(SUM(l.qty),0)<i.safety_stock
        ))"""
    )[0]


def finished_goods_inventory() -> pd.DataFrame:
    return db.dataframe(
        """SELECT i.item_name 제품명,COALESCE(SUM(l.qty),0) 총재고,i.unit 단위
        FROM item i
        LEFT JOIN lot l ON l.item_id=i.item_id AND l.lot_type='PRODUCTION'
        WHERE i.item_type='PRODUCT' AND i.is_active='Y'
        GROUP BY i.item_id,i.item_name,i.unit
        ORDER BY i.item_id"""
    )


def equipment_yield(days: int | None = None) -> pd.DataFrame:
    date_filter = "AND p.production_date>=date('now', ?)" if days is not None else ""
    params = (f"-{days} day",) if days is not None else ()
    return db.dataframe(
        f"""SELECT COALESCE(e.equipment_name, '미지정 설비') 설비,
               COUNT(p.production_id) 생산LOT수,
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
        WHERE p.status = 'COMPLETED' {date_filter}
        GROUP BY p.equipment_id, e.equipment_name
        ORDER BY e.equipment_name""",
        params,
    )


def equipment_defect_counts(days: int = 30) -> pd.DataFrame:
    return db.dataframe(
        """SELECT COALESCE(e.equipment_name,'미지정 설비') 설비,
               dc.defect_code 불량코드, dc.defect_name 불량명,
               COUNT(pd.production_defect_id) 발생횟수,
               SUM(pd.defect_qty) 불량수량
        FROM production_defect pd
        JOIN production p ON p.production_id=pd.production_id
        LEFT JOIN equipment e ON e.equipment_id=p.equipment_id
        JOIN defect_code dc ON dc.defect_code_id=pd.defect_code_id
        WHERE pd.defect_date>=date('now', ?)
        GROUP BY p.equipment_id,e.equipment_name,dc.defect_code_id,
                 dc.defect_code,dc.defect_name
        ORDER BY e.equipment_name,발생횟수 DESC""",
        (f"-{days} day",),
    )


def material_inventory() -> pd.DataFrame:
    return db.dataframe(
        """SELECT i.item_name 품목,COALESCE(SUM(l.qty),0) 총재고,
        i.safety_stock 안전재고,
        CASE WHEN COALESCE(SUM(l.qty),0)<i.safety_stock THEN '경고' ELSE '정상' END 상태
        FROM item i LEFT JOIN lot l ON l.item_id=i.item_id AND l.lot_type='RECEIPT'
        WHERE i.item_type='MATERIAL' AND i.is_active='Y'
        GROUP BY i.item_id,i.item_name,i.safety_stock
        ORDER BY CASE WHEN COALESCE(SUM(l.qty),0)<i.safety_stock THEN 0 ELSE 1 END,i.item_name"""
    )
