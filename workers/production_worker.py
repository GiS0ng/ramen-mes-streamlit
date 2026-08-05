from __future__ import annotations

import logging
import os
import signal
import sys
import threading
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Iterator
from zoneinfo import ZoneInfo

import db
from services import production


LOGGER = logging.getLogger("mes.production_worker")
WORKER_NAME = "production"
KOREA_TIMEZONE = ZoneInfo("Asia/Seoul")
DEFAULT_INTERVAL_SECONDS = 5.0
LOCK_PATH = Path("/tmp/ramen-mes-production-worker.lock")


def _now_text() -> str:
    return datetime.now(KOREA_TIMEZONE).replace(tzinfo=None).isoformat(
        timespec="seconds"
    )


def _record_status(status: str, message: str) -> None:
    with db.transaction() as connection:
        connection.execute(
            """INSERT INTO worker_heartbeat(
                   worker_name,last_run_at,status,message
               ) VALUES(?,?,?,?)
               ON CONFLICT(worker_name) DO UPDATE SET
                   last_run_at=excluded.last_run_at,
                   status=excluded.status,
                   message=excluded.message""",
            (WORKER_NAME, _now_text(), status, message),
        )


def run_cycle() -> list[int]:
    """생산 진행수량을 반영하고 완료 예정 계획을 마감한다."""
    try:
        completed_plan_ids = production.auto_complete_due_plans()
        message = (
            f"자동 완료 {len(completed_plan_ids)}건"
            if completed_plan_ids
            else "가동 계획 확인 완료"
        )
        _record_status("RUNNING", message)
        return completed_plan_ids
    except Exception as exc:
        _record_status("ERROR", str(exc))
        raise


def run_forever(interval_seconds: float = DEFAULT_INTERVAL_SECONDS) -> None:
    if interval_seconds <= 0:
        raise ValueError("Worker 실행 주기는 0초보다 커야 합니다.")

    stop_event = threading.Event()

    def request_stop(signum, frame) -> None:
        del signum, frame
        stop_event.set()

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    LOGGER.info("Production worker started (interval=%ss)", interval_seconds)
    while not stop_event.is_set():
        try:
            run_cycle()
        except Exception:
            LOGGER.exception("Production worker cycle failed")
        stop_event.wait(interval_seconds)
    _record_status("STOPPED", "Worker 정상 종료")
    LOGGER.info("Production worker stopped")


@contextmanager
def singleton_lock() -> Iterator[None]:
    import fcntl

    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOCK_PATH.open("w", encoding="utf-8") as lock_file:
        try:
            fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError("생산 Worker가 이미 실행 중입니다.") from exc
        lock_file.write(str(os.getpid()))
        lock_file.flush()
        yield


def main() -> int:
    logging.basicConfig(
        level=os.environ.get("MES_WORKER_LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    interval_seconds = float(
        os.environ.get("MES_PRODUCTION_INTERVAL_SECONDS", DEFAULT_INTERVAL_SECONDS)
    )
    db.initialize()
    try:
        with singleton_lock():
            run_forever(interval_seconds)
    except RuntimeError as exc:
        LOGGER.error("%s", exc)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
