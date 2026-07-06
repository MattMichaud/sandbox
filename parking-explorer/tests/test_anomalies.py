"""Anomaly detector tests against the real local cache (skipped if empty)."""

from __future__ import annotations

import datetime as dt

import pandas as pd
import pytest

from parking import anomalies, store
from parking.config import DB_PATH


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


pytestmark = pytest.mark.skipif(
    not _has_data(), reason="no local DuckDB data; run sync_cli.py first"
)


@pytest.fixture(scope="module")
def anoms() -> pd.DataFrame:
    con = store.connect(read_only=True)
    try:
        return anomalies.detect(con)
    finally:
        con.close()


def _on(df, day: dt.date):
    return df[pd.to_datetime(df["date"]).dt.date == day]


def test_expected_columns(anoms):
    assert list(anoms.columns) == ["date", "garage", "level", "type", "severity", "detail"]
    assert anoms["severity"].between(0, 1).all()


def test_january_ice_storm(anoms):
    # Data pipeline lost snapshots on Jan 28, 2026 (power outages).
    assert (_on(anoms, dt.date(2026, 1, 28))["type"] == "Collection gap").any()
    # Both garages' peaks collapsed during the storm.
    storm = anoms[
        (anoms["type"] == "Suppressed activity")
        & pd.to_datetime(anoms["date"]).dt.date.between(dt.date(2026, 1, 24), dt.date(2026, 1, 27))
    ]
    assert set(storm["garage"]) == {"Second Avenue", "Fourth Avenue"}


def test_april_second_avenue_partial_closure(anoms):
    window = anoms[
        pd.to_datetime(anoms["date"]).dt.date.between(dt.date(2026, 4, 21), dt.date(2026, 4, 27))
    ]
    # Second Avenue's lower levels flagged; Fourth Avenue untouched that week.
    assert (
        (window["garage"] == "Second Avenue")
        & (window["type"] == "Level emptied")
        & (window["level"] == "Level 1")
    ).any()
    assert (window["garage"] == "Fourth Avenue").sum() == 0
