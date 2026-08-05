from __future__ import annotations

import pandas as pd

import db
from domain.rules import BOX_SIZE


def all_schedules() -> pd.DataFrame:
    return db.dataframe(
        """SELECT ss.shipment_schedule_no 계획번호,
                  bp.partner_name 고객사,i.item_name 제품,
                  CAST(ss.scheduled_qty/? AS INTEGER) 출하계획박스,
                  ss.scheduled_qty 출하계획수량,
                  ss.shipped_qty 출고수량,
                  CAST((ss.scheduled_qty-ss.shipped_qty)/? AS INTEGER) 미출하박스,
                  ss.scheduled_qty-ss.shipped_qty 미출하수량,
                  ss.scheduled_date 출하예정일,
                  CASE ss.status
                      WHEN 'PLANNED' THEN
                          CASE WHEN ss.scheduled_date<date('now')
                               THEN '미출하' ELSE '출하 예정' END
                      WHEN 'PARTIAL_SHIPPED' THEN '부분 출고'
                      WHEN 'SHIPPED' THEN '출고 완료'
                      WHEN 'CANCELED' THEN '취소'
                  END 상태
           FROM shipment_schedule ss
           JOIN business_partner bp ON bp.partner_id=ss.customer_id
           JOIN item i ON i.item_id=ss.item_id
           ORDER BY ss.scheduled_date DESC,ss.shipment_schedule_id DESC""",
        (BOX_SIZE, BOX_SIZE),
    )


def pending_schedules() -> pd.DataFrame:
    return db.dataframe(
        """WITH available_box AS (
               SELECT p.item_id,pb.packing_box_id
               FROM packing_box pb
               JOIN packing_box_detail pbd USING(packing_box_id)
               JOIN lot l ON l.lot_id=pbd.product_lot_id
               JOIN production p ON p.output_lot_id=l.lot_id
               LEFT JOIN shipment_box sb USING(packing_box_id)
               WHERE sb.shipment_box_id IS NULL
                 AND NOT EXISTS(
                     SELECT 1 FROM production_defect pd
                     WHERE pd.production_id=p.production_id
                 )
               GROUP BY p.item_id,pb.packing_box_id
               HAVING COUNT(*)=?
                  AND SUM(CASE WHEN l.qty>=1 THEN 1 ELSE 0 END)=?
           ), box_stock AS (
               SELECT item_id,COUNT(*) box_qty
               FROM available_box GROUP BY item_id
           )
           SELECT ss.shipment_schedule_id 출하계획ID,
                  ss.shipment_schedule_no 계획번호,
                  bp.partner_name 고객사,i.item_name 제품,
                  ss.scheduled_date 출하예정일,
                  CAST((ss.scheduled_qty-ss.shipped_qty)/? AS INTEGER) 미출하박스,
                  ss.scheduled_qty-ss.shipped_qty 미출하수량,
                  COALESCE(bs.box_qty,0)*? 현재재고,
                  COALESCE(bs.box_qty,0) 출고가능박스,
                  CASE WHEN COALESCE(bs.box_qty,0)>=
                                 (ss.scheduled_qty-ss.shipped_qty)/?
                       THEN 1 ELSE 0 END 출고가능
           FROM shipment_schedule ss
           JOIN business_partner bp ON bp.partner_id=ss.customer_id
           JOIN item i ON i.item_id=ss.item_id
           LEFT JOIN box_stock bs ON bs.item_id=ss.item_id
           WHERE ss.status IN ('PLANNED','PARTIAL_SHIPPED')
             AND ss.shipped_qty<ss.scheduled_qty
           ORDER BY ss.scheduled_date,ss.shipment_schedule_id""",
        (BOX_SIZE, BOX_SIZE, BOX_SIZE, BOX_SIZE, BOX_SIZE),
    )


def completed_shipments() -> pd.DataFrame:
    return db.dataframe(
        """SELECT s.shipment_no 출고번호,
                  ss.shipment_schedule_no 계획번호,
                  bp.partner_name 고객사,i.item_name 제품,
                  (SELECT COUNT(*) FROM shipment_box sb
                   WHERE sb.shipment_id=s.shipment_id) 출고박스,
                  (SELECT GROUP_CONCAT(pb.box_no, ', ')
                   FROM shipment_box sb JOIN packing_box pb USING(packing_box_id)
                   WHERE sb.shipment_id=s.shipment_id) 출고박스번호,
                  (SELECT SUM(sd.shipment_qty) FROM shipment_detail sd
                   WHERE sd.shipment_id=s.shipment_id) 출고수량,
                  s.shipment_date 출고일,
                  (SELECT COUNT(*) FROM shipment_detail sd
                   WHERE sd.shipment_id=s.shipment_id) 출고LOT수
           FROM shipment s
           JOIN shipment_schedule ss USING(shipment_schedule_id)
           JOIN business_partner bp ON bp.partner_id=s.customer_id
           JOIN item i ON i.item_id=ss.item_id
           WHERE s.status='SHIPPED'
           ORDER BY s.shipment_date DESC,s.shipment_id DESC"""
    )
