"""Smoke test: run the whole Streamlit script headlessly and assert no error.

Exercises every query + Altair spec against the real local cache. Skipped when
the cache is empty (run ``poetry run python sync_cli.py`` first).
"""

from __future__ import annotations

import pytest

from parking import store
from parking.config import DB_PATH, PROJECT_ROOT


def _has_data() -> bool:
    if not DB_PATH.exists():
        return False
    con = store.connect(read_only=True)
    try:
        return store.row_count(con) > 0
    except Exception:
        return False
    finally:
        con.close()


@pytest.mark.skipif(not _has_data(), reason="no local DuckDB data; run sync_cli.py first")
def test_app_runs_without_exception():
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(PROJECT_ROOT / "app.py"), default_timeout=90).run()
    assert not at.exception, at.exception
    # All five tabs' content executed without error.
    assert len(at.tabs) == 5


@pytest.mark.skipif(not _has_data(), reason="no local DuckDB data; run sync_cli.py first")
def test_app_handles_full_date_range():
    """Regression: the Data tab used to crash on wide ranges via pandas Styler's
    cell cap. Drive the date range to the whole history and assert it renders."""
    from streamlit.testing.v1 import AppTest

    con = store.connect(read_only=True)
    try:
        lo, hi = con.execute("SELECT min(ts_local)::DATE, max(ts_local)::DATE FROM parking").fetchone()
    finally:
        con.close()

    at = AppTest.from_file(str(PROJECT_ROOT / "app.py"), default_timeout=120).run()
    at.date_input[0].set_value((lo, hi)).run()
    assert not at.exception, at.exception
