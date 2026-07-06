"""Turn one raw DynamoDB item's ``api_response`` tree into tidy long rows.

The API returns a recursive tree::

    City of Franklin (system)
      -> Second Avenue (garage)
           -> Level 3 (level)
                -> Zone 1 (zone)

Every node carries ``Name`` / ``TotalBays`` / ``OccupiedBays``. We emit one row
per node, tagged with its depth (``node_type``) and its ancestry
(``garage`` / ``level`` / ``zone``), so the app can slice at any granularity.
"""

from __future__ import annotations

import datetime as dt
from typing import Any
from zoneinfo import ZoneInfo

from .config import LOCAL_TZ

_UTC = ZoneInfo("UTC")
_LOCAL = ZoneInfo(LOCAL_TZ)

# Depth in the tree -> human label. Depth 0 is the whole system (the root).
_NODE_TYPES = {0: "system", 1: "garage", 2: "level", 3: "zone"}

# Column order is the contract shared with the DuckDB schema in store.py.
COLUMNS = [
    "request_timestamp",
    "ts_utc",
    "ts_local",
    "node_type",
    "garage",
    "level",
    "zone",
    "name",
    "path",
    "total_bays",
    "occupied_bays",
    "available_bays",
    "occupancy_pct",
]


def parse_timestamp(raw: str) -> dt.datetime:
    """Parse ``request_timestamp`` into an aware UTC datetime.

    The Lambda writes naive ISO strings (e.g. ``2026-04-17T01:45:36.669559``);
    some historical rows may carry a trailing ``Z`` or an offset. We normalize
    all of those and treat naive values as UTC.
    """
    s = raw.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    parsed = dt.datetime.fromisoformat(s)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=_UTC)
    return parsed.astimezone(_UTC)


def flatten_response(api: dict[str, Any], request_timestamp: str) -> list[dict]:
    """Flatten one ``api_response`` dict into a list of row dicts."""
    ts_utc_aware = parse_timestamp(request_timestamp)
    ts_utc = ts_utc_aware.replace(tzinfo=None)
    ts_local = ts_utc_aware.astimezone(_LOCAL).replace(tzinfo=None)

    rows: list[dict] = []

    def walk(node: dict, ancestry: list[str], depth: int) -> None:
        total = int(node.get("TotalBays") or 0)
        occupied = int(node.get("OccupiedBays") or 0)
        name = node.get("Name")
        # ancestry holds the names from the garage level down (empty at root).
        path = " > ".join(ancestry) if ancestry else (name or "root")
        rows.append(
            {
                "request_timestamp": request_timestamp,
                "ts_utc": ts_utc,
                "ts_local": ts_local,
                "node_type": _NODE_TYPES.get(depth, f"depth_{depth}"),
                "garage": ancestry[0] if len(ancestry) >= 1 else None,
                "level": ancestry[1] if len(ancestry) >= 2 else None,
                "zone": ancestry[2] if len(ancestry) >= 3 else None,
                "name": name,
                "path": path,
                "total_bays": total,
                "occupied_bays": occupied,
                "available_bays": total - occupied,
                "occupancy_pct": (occupied / total * 100.0) if total else None,
            }
        )
        for child in node.get("Zones") or []:
            walk(child, ancestry + [child.get("Name")], depth + 1)

    walk(api, [], 0)
    return rows
