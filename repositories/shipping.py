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
        """WITH product_stock AS (
               SELECT item_id,COALESCE(SUM(qty),0) stock_qty
               FROM lot
               WHERE lot_type='PRODUCTION' AND qty>0
               GROUP BY item_id
           )
           SELECT ss.shipment_schedule_id 출하계획ID,
                  ss.shipment_schedule_no 계획번호,
                  bp.partner_name 고객사,i.item_name 제품,
                  ss.scheduled_date 출하예정일,
                  CAST((ss.scheduled_qty-ss.shipped_qty)/? AS INTEGER) 미출하박스,
                  ss.scheduled_qty-ss.shipped_qty 미출하수량,
                  COALESCE(ps.stock_qty,0) 현재재고,
                  CAST(COALESCE(ps.stock_qty,0)/? AS INTEGER) 출고가능박스,
                  CASE WHEN COALESCE(ps.stock_qty,0)>=
                                 ss.scheduled_qty-ss.shipped_qty
                       THEN 1 ELSE 0 END 출고가능
           FROM shipment_schedule ss
           JOIN business_partner bp ON bp.partner_id=ss.customer_id
           JOIN item i ON i.item_id=ss.item_id
           LEFT JOIN product_stock ps ON ps.item_id=ss.item_id
           WHERE ss.status IN ('PLANNED','PARTIAL_SHIPPED')
             AND ss.shipped_qty<ss.scheduled_qty
           ORDER BY ss.scheduled_date,ss.shipment_schedule_id""",
        (BOX_SIZE, BOX_SIZE),
    )


def completed_shipments() -> pd.DataFrame:
    return db.dataframe(
        """SELECT s.shipment_no 출고번호,
                  ss.shipment_schedule_no 계획번호,
                  bp.partner_name 고객사,i.item_name 제품,
                  CAST(SUM(sd.shipment_qty)/? AS INTEGER) 출고박스,
                  SUM(sd.shipment_qty) 출고수량,
                  s.shipment_date 출고일,
                  COUNT(sd.shipment_detail_id) 출고LOT수
           FROM shipment s
           JOIN shipment_schedule ss USING(shipment_schedule_id)
           JOIN business_partner bp ON bp.partner_id=s.customer_id
           JOIN item i ON i.item_id=ss.item_id
           JOIN shipment_detail sd USING(shipment_id)
           WHERE s.status='SHIPPED'
           GROUP BY s.shipment_id
           ORDER BY s.shipment_date DESC,s.shipment_id DESC""",
        (BOX_SIZE,),
    )
