from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Sequence

import pandas as pd

from domain.rules import RAW_MATERIAL_SAFETY_STOCK


ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
DB_PATH = DATA_DIR / "mes.db"
SCHEMA_PATH = ROOT / "schema.sql"


def connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(exist_ok=True)
    connection = sqlite3.connect(DB_PATH, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


@contextmanager
def transaction():
    connection = connect()
    try:
        connection.execute("BEGIN IMMEDIATE")
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def initialize() -> None:
    with connect() as connection:
        connection.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        connection.commit()
    seed_masters()


def execute(sql: str, params: Sequence = ()) -> int:
    with transaction() as connection:
        cursor = connection.execute(sql, params)
        return int(cursor.lastrowid)


def query(sql: str, params: Sequence = ()) -> list[sqlite3.Row]:
    with connect() as connection:
        return connection.execute(sql, params).fetchall()


def dataframe(sql: str, params: Sequence = ()) -> pd.DataFrame:
    with connect() as connection:
        return pd.read_sql_query(sql, connection, params=params)


def options(sql: str, params: Sequence = ()) -> dict[str, int]:
    return {str(row[1]): int(row[0]) for row in query(sql, params)}


def seed_masters() -> None:
    with transaction() as connection:
        connection.executemany(
            "INSERT OR IGNORE INTO item(item_code,item_name,item_type,unit,safety_stock) VALUES(?,?,?,?,?)",
            [
                ("RM-NOODLE", "라면 면", "MATERIAL", "EA", RAW_MATERIAL_SAFETY_STOCK),
                ("RM-SOUP", "분말 스프", "MATERIAL", "EA", RAW_MATERIAL_SAFETY_STOCK),
                ("RM-PACK", "포장지", "MATERIAL", "EA", RAW_MATERIAL_SAFETY_STOCK),
                ("FG-RAMEN", "봉지 라면", "PRODUCT", "EA", RAW_MATERIAL_SAFETY_STOCK),
            ],
        )
        connection.executemany(
            "INSERT OR IGNORE INTO business_partner(partner_code,partner_name,partner_type) VALUES(?,?,?)",
            [("SUP-001", "대한식품원료", "SUPPLIER"), ("CUS-001", "행복마트", "CUSTOMER")],
        )
        connection.execute(
            "INSERT OR IGNORE INTO equipment(equipment_code,equipment_name,equipment_type,location) VALUES(?,?,?,?)",
            ("EQ-PACK-01", "라면 포장 1호기", "포장설비", "1공장"),
        )
        connection.executemany(
            "INSERT OR IGNORE INTO defect_code(defect_code,defect_name,description) VALUES(?,?,?)",
            [
                ("DEF-PACK", "포장 불량", "포장지 파손, 밀봉 또는 인쇄 불량"),
                ("DEF-NOODLE-MISSING", "면 누락", "완제품 내부 면 블록 누락"),
                ("DEF-SOUP-MISSING", "스프 누락", "완제품 내부 스프 누락"),
            ],
        )


def reset_demo() -> None:
    initialize()
    tables = [
        "equipment_operation", "production_defect", "defect_code",
        "shipment_detail", "shipment", "shipment_schedule", "packing_box_detail", "packing_box",
        "product_box", "production_request_unit", "production_request", "material_receipt",
        "purchase_order_detail", "purchase_order", "production_material",
        "production", "lot", "equipment", "business_partner", "item",
    ]
    connection = connect()
    try:
        connection.execute("PRAGMA foreign_keys = OFF")
        for table in tables:
            connection.execute(f"DELETE FROM {table}")
        connection.commit()
    finally:
        connection.close()
    seed_masters()


def seed_demo(days: int = 30, seed: int = 20260803) -> None:
    """공개 API 호환성을 유지하면서 전용 더미 데이터 모듈에 위임한다."""
    from seed import seed_demo as build_demo

    build_demo(days=days, seed=seed)


def create_production_request(
    request_no: str,
    product_id: int,
    equipment_id: int | None,
    production_date: str,
    requested_qty: int,
) -> int:
    """이전 호출 호환성을 위해 생산 서비스에 위임한다."""
    from services.production import create_request

    return create_request(request_no, product_id, equipment_id, production_date, requested_qty)
