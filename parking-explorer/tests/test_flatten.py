"""Unit tests for the flattener + timestamp parsing (no AWS/DuckDB needed)."""

from __future__ import annotations

import datetime as dt

from parking.flatten import flatten_response, parse_timestamp

SAMPLE = {
    "Name": "City of Franklin",
    "TotalBays": 590,
    "OccupiedBays": 331,
    "Zones": [
        {
            "Name": "Second Avenue",
            "TotalBays": 257,
            "OccupiedBays": 132,
            "Zones": [
                {"Name": "Level 4", "TotalBays": 40, "OccupiedBays": 1},
                {
                    "Name": "Level 3",
                    "TotalBays": 80,
                    "OccupiedBays": 43,
                    "Zones": [{"Name": "Zone 1", "TotalBays": 80, "OccupiedBays": 43}],
                },
                {"Name": "Level 1 EV", "TotalBays": 0, "OccupiedBays": 0},
            ],
        }
    ],
}


def _rows():
    return flatten_response(SAMPLE, "2026-04-17T01:45:36.669559")


def test_parse_timestamp_variants_are_utc():
    naive = parse_timestamp("2026-04-17T01:45:36.669559")
    zulu = parse_timestamp("2026-04-17T01:45:36.669559Z")
    assert naive.utcoffset() == dt.timedelta(0)
    assert naive == zulu


def test_local_conversion_uses_central():
    rows = _rows()
    # 01:45 UTC on Apr 17 (CDT, UTC-5) -> 20:45 the previous evening, Apr 16.
    system = next(r for r in rows if r["node_type"] == "system")
    assert system["ts_local"].hour == 20
    assert system["ts_local"].day == 16


def test_node_types_and_ancestry():
    rows = _rows()
    by_type = {}
    for r in rows:
        by_type.setdefault(r["node_type"], []).append(r)

    assert len(by_type["system"]) == 1
    assert len(by_type["garage"]) == 1
    assert len(by_type["level"]) == 3
    assert len(by_type["zone"]) == 1

    zone = by_type["zone"][0]
    assert zone["garage"] == "Second Avenue"
    assert zone["level"] == "Level 3"
    assert zone["zone"] == "Zone 1"
    assert zone["path"] == "Second Avenue > Level 3 > Zone 1"


def test_derived_metrics_and_zero_capacity():
    rows = _rows()
    system = next(r for r in rows if r["node_type"] == "system")
    assert system["available_bays"] == 590 - 331
    assert abs(system["occupancy_pct"] - (331 / 590 * 100)) < 1e-9

    ev = next(r for r in rows if r["name"] == "Level 1 EV")
    assert ev["total_bays"] == 0
    assert ev["occupancy_pct"] is None  # no divide-by-zero


def test_paths_are_unique_within_snapshot():
    rows = _rows()
    paths = [r["path"] for r in rows]
    assert len(paths) == len(set(paths))
