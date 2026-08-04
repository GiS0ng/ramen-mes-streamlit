from __future__ import annotations

import db


def create_item(code: str, name: str, item_type: str, unit: str, safety_stock: float) -> int:
    return db.execute(
        "INSERT INTO item(item_code,item_name,item_type,unit,safety_stock) VALUES(?,?,?,?,?)",
        (code, name, item_type, unit, safety_stock),
    )


def create_partner(code: str, name: str, partner_type: str, phone: str, email: str, address: str) -> int:
    return db.execute(
        "INSERT INTO business_partner(partner_code,partner_name,partner_type,phone,email,address) VALUES(?,?,?,?,?,?)",
        (code, name, partner_type, phone, email, address),
    )


def create_equipment(code: str, name: str, equipment_type: str, location: str) -> int:
    return db.execute(
        "INSERT INTO equipment(equipment_code,equipment_name,equipment_type,location) VALUES(?,?,?,?)",
        (code, name, equipment_type, location),
    )
