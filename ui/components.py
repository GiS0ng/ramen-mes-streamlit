from __future__ import annotations

import sqlite3
from collections.abc import Callable, Sequence
from typing import Any, TypeVar

import pandas as pd
import streamlit as st

import db


T = TypeVar("T")


def run_action(action: Callable[[], T], success: str) -> None:
    """업무 작업을 실행하고 Streamlit 공통 메시지를 표시한다."""
    try:
        action()
        st.success(success)
        st.rerun()
    except sqlite3.IntegrityError as exc:
        st.error(str(exc).replace("UNIQUE constraint failed:", "중복 값:"))
    except Exception as exc:
        st.error(f"처리 중 오류가 발생했습니다: {exc}")


def select_id(label: str, options: dict[str, int], key: str | None = None) -> int | None:
    """표시 이름과 ID가 매핑된 선택 상자를 렌더링한다."""
    if not options:
        st.warning(f"선택 가능한 {label} 데이터가 없습니다.")
        return None
    name = st.selectbox(label, list(options), key=key)
    return options[name]


def grid(sql: str, params: Sequence[Any] = (), height: int = 310) -> pd.DataFrame:
    """SQL 조회 결과를 공통 표 형식으로 표시한다."""
    frame = db.dataframe(sql, params)
    show_frame(frame, height)
    return frame


def show_frame(frame: pd.DataFrame, height: int = 310) -> None:
    """이미 조회된 데이터프레임을 공통 표 형식으로 표시한다."""
    st.dataframe(frame, width="stretch", hide_index=True, height=height)
