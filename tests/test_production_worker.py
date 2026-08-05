import sys
from pathlib import Path

import pytest


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import db
from workers import production_worker


@pytest.fixture(scope="module", autouse=True)
def initialized_worker_database():
    db.seed_demo()


def test_worker_cycle_records_heartbeat(monkeypatch):
    monkeypatch.setattr(
        production_worker.production,
        "auto_complete_due_plans",
        lambda: [101, 102],
    )
    assert production_worker.run_cycle() == [101, 102]
    status, message = db.query(
        """SELECT status,message FROM worker_heartbeat
           WHERE worker_name='production'"""
    )[0]
    assert status == "RUNNING"
    assert message == "자동 완료 2건"


def test_worker_cycle_records_error(monkeypatch):
    def fail_cycle():
        raise ValueError("테스트 생산 오류")

    monkeypatch.setattr(
        production_worker.production,
        "auto_complete_due_plans",
        fail_cycle,
    )
    with pytest.raises(ValueError, match="테스트 생산 오류"):
        production_worker.run_cycle()
    status, message = db.query(
        """SELECT status,message FROM worker_heartbeat
           WHERE worker_name='production'"""
    )[0]
    assert status == "ERROR"
    assert message == "테스트 생산 오류"
