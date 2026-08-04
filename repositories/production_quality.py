from __future__ import annotations

import pandas as pd

import db


def production_dates(equipment_id: int) -> list[str]:
    return [
        str(row[0])
        for row in db.query(
            """SELECT DISTINCT production_date
               FROM production
               WHERE equipment_id=? AND status='COMPLETED'
               ORDER BY production_date DESC""",
            (equipment_id,),
        )
    ]


def production_lot_options(equipment_id: int, production_date: str) -> dict[str, int]:
    return db.options(
        """SELECT p.production_id,
                  l.lot_no||' · '||i.item_name||' · '||p.production_no
           FROM production p
           JOIN lot l ON l.lot_id=p.output_lot_id
           JOIN item i ON i.item_id=p.item_id
           WHERE p.equipment_id=? AND p.production_date=? AND p.status='COMPLETED'
           ORDER BY l.lot_no""",
        (equipment_id, production_date),
    )


def defective_products() -> pd.DataFrame:
    return db.dataframe(
        """SELECT e.equipment_name 불량설비,p.production_date 생산일,
                  pd.defect_date 불량발생일,i.item_name 완제품,
                  l.lot_no 완제품LOT,p.production_no 생산번호,
                  dc.defect_code 불량코드,dc.defect_name 불량유형,
                  pd.defect_qty 불량수량,pd.memo 비고
           FROM production_defect pd
           JOIN production p ON p.production_id=pd.production_id
           LEFT JOIN equipment e ON e.equipment_id=p.equipment_id
           JOIN item i ON i.item_id=p.item_id
           JOIN lot l ON l.lot_id=p.output_lot_id
           JOIN defect_code dc ON dc.defect_code_id=pd.defect_code_id
           ORDER BY pd.defect_date DESC,p.production_date DESC,l.lot_no"""
    )


def production_plans() -> pd.DataFrame:
    return db.dataframe(
        """SELECT pr.request_no 계획번호,e.equipment_name 설비,
                  i.item_name 품목,pr.requested_qty 생산수량,
                  e.capacity_per_minute 분당생산능력,
                  ROUND(pr.requested_qty/NULLIF(e.capacity_per_minute,0),2) 예상포장시간_분,
                  pr.request_date 등록일,pr.status 상태
           FROM production_request pr
           JOIN item i ON i.item_id=pr.item_id
           LEFT JOIN equipment e ON e.equipment_id=pr.equipment_id
           WHERE pr.status='PLANNED'
           ORDER BY pr.request_date DESC,pr.production_request_id DESC"""
    )
