from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest


ROOT = Path(__file__).resolve().parents[1]
PAGE_FILES = [
    "app.py",
    "pages/dashboard.py",
    "pages/master_data.py",
    "pages/purchasing.py",
    "pages/production_quality.py",
    "pages/shipping.py",
    "pages/traceability.py",
    "pages/equipment.py",
]


@pytest.mark.parametrize("relative_path", PAGE_FILES)
def test_streamlit_page_loads_without_exception(relative_path: str):
    app = AppTest.from_file(str(ROOT / relative_path))
    app.run(timeout=60)
    assert not app.exception
