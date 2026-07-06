"""Unit tests for the DuckDB store (temp DB, no AWS)."""

from __future__ import annotations

import datetime as dt

from parking import store
from parking.flatten import COLUMNS


def _row(ts: dt.datetime, rt: str) -> dict:
    base = {c: None for c in COLUMNS}
    base.update(
        request_timestamp=rt, ts_utc=ts, ts_local=ts, node_type="system",
        path="root", total_bays=10, occupied_bays=5, available_bays=5,
        occupancy_pct=50.0,
    )
    return base


def test_prune_before(tmp_path):
    con = store.connect(db_path=tmp_path / "t.duckdb")
    store.init_schema(con)
    store.insert_rows(
        con,
        [
            _row(dt.datetime(2025, 2, 10, 12), "2025-02-10T18:00:00"),  # before cutoff
            _row(dt.datetime(2025, 8, 25, 12), "2025-08-25T17:00:00"),  # after
            _row(dt.datetime(2026, 1, 1, 12), "2026-01-01T18:00:00"),  # after
        ],
    )
    assert store.row_count(con) == 3

    assert store.prune_before(con, None) == 0  # no cutoff -> no-op
    assert store.row_count(con) == 3

    removed = store.prune_before(con, dt.date(2025, 8, 20))
    assert removed == 1
    assert store.row_count(con) == 2
    con.close()


def test_insert_is_idempotent(tmp_path):
    con = store.connect(db_path=tmp_path / "t.duckdb")
    store.init_schema(con)
    rows = [_row(dt.datetime(2026, 1, 1, 12), "2026-01-01T18:00:00")]
    assert store.insert_rows(con, rows) == 1
    assert store.insert_rows(con, rows) == 0  # same key -> ignored
    assert store.row_count(con) == 1
    con.close()
