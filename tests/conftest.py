from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

import db


@pytest.fixture(scope="session", autouse=True)
def isolated_database(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Path]:
    """테스트가 사용자의 로컬 MES 데이터베이스를 변경하지 않도록 격리한다."""
    original_path = db.DB_PATH
    test_path = tmp_path_factory.mktemp("mes-data") / "mes-test.db"
    db.DB_PATH = test_path
    db.initialize()
    try:
        yield test_path
    finally:
        db.DB_PATH = original_path
