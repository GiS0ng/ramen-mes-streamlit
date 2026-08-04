from __future__ import annotations

import pandas as pd

import db


def material_options() -> dict[str, int]:
    return db.options(
        """SELECT item_id,item_code||' · '||item_name
        FROM item
        WHERE item_type='MATERIAL' AND is_active='Y'
        ORDER BY item_code"""
    )


def raw_material_options(
    material_item_id: int | None = None,
    receipt_start_date: str | None = None,
    receipt_end_date: str | None = None,
) -> dict[str, int]:
    return db.options(
        """SELECT l.lot_id,l.lot_no||' · '||i.item_name
        FROM lot l JOIN item i USING(item_id)
        WHERE l.lot_type='RECEIPT'
          AND (? IS NULL OR i.item_id=?)
          AND (? IS NULL OR l.received_date>=?)
          AND (? IS NULL OR l.received_date<=?)
        ORDER BY l.received_date DESC,l.lot_no"""
        ,
        (
            material_item_id,
            material_item_id,
            receipt_start_date,
            receipt_start_date,
            receipt_end_date,
            receipt_end_date,
        ),
    )


def customer_options() -> dict[str, int]:
    return db.options(
        """SELECT partner_id,partner_code||' · '||partner_name
        FROM business_partner
        WHERE partner_type IN ('CUSTOMER','BOTH') AND is_active='Y'
        ORDER BY partner_code"""
    )


def raw_material_to_products(raw_lot_id: int, start_date: str, end_date: str) -> pd.DataFrame:
    return db.dataframe(
        """SELECT ml.lot_no 원재료LOT,mi.item_name 원재료,
               p.production_no 생산번호,p.production_date 생산일,
               pl.lot_no 완제품LOT,pi.item_code 제품코드,pi.item_name 제품,
               pm.qty 투입량
        FROM production_material pm
        JOIN lot ml ON ml.lot_id=pm.material_lot_id
        JOIN item mi ON mi.item_id=ml.item_id
        JOIN production p ON p.production_id=pm.production_id
        JOIN lot pl ON pl.lot_id=p.output_lot_id
        JOIN item pi ON pi.item_id=p.item_id
        WHERE ml.lot_id=? AND p.production_date BETWEEN ? AND ?
        ORDER BY p.production_date DESC,p.production_no""",
        (raw_lot_id, start_date, end_date),
    )


def raw_material_to_shipments(
    raw_lot_id: int,
    start_date: str,
    end_date: str,
    customer_id: int | None = None,
) -> pd.DataFrame:
    return db.dataframe(
        """SELECT ml.lot_no 원재료LOT,mi.item_name 원재료,
               p.production_no 생산번호,pl.lot_no 완제품LOT,pi.item_name 제품,
               bp.partner_code 고객코드,bp.partner_name 고객사,
               s.shipment_no 출하번호,s.shipment_date 출하일,
               sd.shipment_qty 출하량
        FROM production_material pm
        JOIN lot ml ON ml.lot_id=pm.material_lot_id
        JOIN item mi ON mi.item_id=ml.item_id
        JOIN production p ON p.production_id=pm.production_id
        JOIN lot pl ON pl.lot_id=p.output_lot_id
        JOIN item pi ON pi.item_id=p.item_id
        JOIN shipment_detail sd ON sd.product_lot_id=pl.lot_id
        JOIN shipment s ON s.shipment_id=sd.shipment_id
        JOIN business_partner bp ON bp.partner_id=s.customer_id
        WHERE ml.lot_id=?
          AND s.shipment_date BETWEEN ? AND ?
          AND (? IS NULL OR bp.partner_id=?)
        ORDER BY s.shipment_date DESC,s.shipment_no""",
        (raw_lot_id, start_date, end_date, customer_id, customer_id),
    )
