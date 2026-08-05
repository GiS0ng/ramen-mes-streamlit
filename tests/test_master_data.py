import sys
from pathlib import Path

import pytest


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import db
from services import master_data


@pytest.fixture(scope="module", autouse=True)
def seeded_master_data():
    db.seed_demo()


def test_equipment_code_accepts_pack_prefix_with_numeric_suffix():
    equipment_id = master_data.create_equipment(
        "EQ-PACK-99", "테스트 포장기", "포장설비", "테스트 위치", 2
    )
    code = db.query(
        "SELECT equipment_code FROM equipment WHERE equipment_id=?",
        (equipment_id,),
    )[0][0]
    assert code == "EQ-PACK-99"


@pytest.mark.parametrize("code", ["99", "EQ-PACK-AA", "EQ-OTHER-03"])
def test_equipment_code_rejects_non_pack_or_non_numeric_suffix(code):
    with pytest.raises(ValueError, match="EQ-PACK-"):
        master_data.create_equipment(
            code, "잘못된 설비", "포장설비", "테스트 위치", 2
        )
