"""DuckDB persistence layer for the local parking cache.

The cache is a single ``parking.duckdb`` file holding one row per hierarchy node
per snapshot. ``(request_timestamp, path)`` is the primary key so re-running a
sync is idempotent (``ON CONFLICT DO NOTHING``).
"""

from __future__ import annotations

import duckdb
import pandas as pd

from .config import DB_PATH
from .flatten import COLUMNS

_SCHEMA = """
CREATE TABLE IF NOT EXISTS parking (
    request_timestamp VARCHAR NOT NULL,
    ts_utc            TIMESTAMP,
    ts_local          TIMESTAMP,
    node_type         VARCHAR,
    garage            VARCHAR,
    level             VARCHAR,
    zone              VARCHAR,
    name              VARCHAR,
    path              VARCHAR NOT NULL,
    total_bays        INTEGER,
    occupied_bays     INTEGER,
    available_bays    INTEGER,
    occupancy_pct     DOUBLE,
    PRIMARY KEY (request_timestamp, path)
);
"""

_COL_LIST = ", ".join(COLUMNS)


def connect(read_only: bool = False, db_path=None) -> duckdb.DuckDBPyConnection:
    """Open a short-lived connection. Use ``read_only=True`` for app queries."""
    return duckdb.connect(str(db_path or DB_PATH), read_only=read_only)


def init_schema(con: duckdb.DuckDBPyConnection) -> None:
    con.execute(_SCHEMA)


def get_last_timestamp(con: duckdb.DuckDBPyConnection) -> str | None:
    """Newest ``request_timestamp`` already cached, or None if empty."""
    row = con.execute("SELECT max(request_timestamp) FROM parking").fetchone()
    return row[0] if row and row[0] is not None else None


def row_count(con: duckdb.DuckDBPyConnection) -> int:
    return con.execute("SELECT count(*) FROM parking").fetchone()[0]


def prune_before(con: duckdb.DuckDBPyConnection, start_date) -> int:
    """Delete cached rows older than ``start_date`` (local). Returns rows removed.

    No-op when ``start_date`` is None. Called on every sync so the cutoff stays
    enforced even if the cache is rebuilt.
    """
    if start_date is None:
        return 0
    before = row_count(con)
    con.execute("DELETE FROM parking WHERE ts_local < ?", [start_date])
    return before - row_count(con)


def insert_rows(con: duckdb.DuckDBPyConnection, rows: list[dict]) -> int:
    """Insert flattened rows, ignoring any that already exist. Returns net new."""
    if not rows:
        return 0
    df = pd.DataFrame(rows, columns=COLUMNS)
    before = row_count(con)
    con.register("incoming", df)
    con.execute(
        f"INSERT INTO parking ({_COL_LIST}) "
        f"SELECT {_COL_LIST} FROM incoming ON CONFLICT DO NOTHING"
    )
    con.unregister("incoming")
    return row_count(con) - before
