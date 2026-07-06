"""Heuristic anomaly detection over the parking history.

Every detector compares a day against *that series' own* baseline, so it adapts
to each garage/level instead of using a global threshold:

* **Collection gap** — far fewer snapshots than a normal day (data-pipeline
  issue, e.g. the power outage during the Jan 2026 ice storm).
* **Suppressed activity** — a garage's daily *peak* occupancy collapses vs its
  typical peak for that weekday (e.g. the ice storm emptied both garages).
* **Level outage** — a normally-used level goes empty, freezes (a stuck
  counter), or runs far below its own norm while capacity is unchanged (e.g. the
  Apr 2026 partial closure of Second Avenue's lower levels).

Detectors only judge occupancy on days with a near-full snapshot count, so a
collection gap is never double-reported as suppressed activity.
"""

from __future__ import annotations

import pandas as pd

# --- Tunables (fractions of each series' own baseline) ---
GAP_RATIO = 0.9  # a day below this fraction of a normal day's snapshots = gap
MIN_FULL_SNAPS_RATIO = 0.7  # need this fraction of a full day before judging occupancy
PEAK_RATIO = 0.5  # garage peak below this fraction of its weekday-typical peak
MIN_TYP_PEAK = 20.0  # only judge garages that normally get reasonably busy
LEVEL_REDUCED_RATIO = 0.2  # level peak below this fraction of its own norm
MIN_TYP_LEVEL_MAX = 5.0  # only judge levels that are normally used

_COLUMNS = ["date", "garage", "level", "type", "severity", "detail"]


def detect(con) -> pd.DataFrame:
    """Return a DataFrame of anomalies, newest and most severe first."""
    counts = con.execute(
        "SELECT ts_local::DATE AS day, count(DISTINCT request_timestamp) AS snaps "
        "FROM parking GROUP BY 1 ORDER BY 1"
    ).df()
    if counts.empty:
        return pd.DataFrame(columns=_COLUMNS)

    expected = int(counts["snaps"].median())
    first_day, last_day = counts["day"].min(), counts["day"].max()
    min_full = int(MIN_FULL_SNAPS_RATIO * expected)

    records: list[dict] = []

    # 1) Collection gaps (skip the naturally-partial first/last days).
    for _, r in counts.iterrows():
        if r["day"] in (first_day, last_day) or r["snaps"] >= GAP_RATIO * expected:
            continue
        records.append(
            {
                "date": r["day"], "garage": "All", "level": "",
                "type": "Collection gap",
                "severity": round(1 - r["snaps"] / expected, 2),
                "detail": f"{int(r['snaps'])}/{expected} snapshots logged",
            }
        )

    # 2) Suppressed garage peak vs weekday-typical peak.
    sup = con.execute(
        """
        WITH daily AS (
            SELECT garage, ts_local::DATE AS day, dayname(ts_local) AS dow,
                   count(DISTINCT request_timestamp) AS snaps,
                   max(occupancy_pct) AS peak
            FROM parking WHERE node_type='garage' GROUP BY 1, 2, 3
        ),
        base AS (SELECT garage, dow, median(peak) AS typ_peak FROM daily GROUP BY 1, 2)
        SELECT d.garage, d.day, d.peak, b.typ_peak
        FROM daily d JOIN base b USING (garage, dow)
        WHERE d.snaps >= ? AND b.typ_peak >= ? AND d.peak < ? * b.typ_peak
        ORDER BY d.day
        """,
        [min_full, MIN_TYP_PEAK, PEAK_RATIO],
    ).df()
    for _, r in sup.iterrows():
        records.append(
            {
                "date": r["day"], "garage": r["garage"], "level": "",
                "type": "Suppressed activity",
                "severity": round(1 - r["peak"] / r["typ_peak"], 2),
                "detail": f"peak {r['peak']:.0f}% vs typical {r['typ_peak']:.0f}% for this weekday",
            }
        )

    # 3) Level outages vs the level's own baseline.
    lvl = con.execute(
        """
        WITH lvl AS (
            SELECT garage, level, ts_local::DATE AS day,
                   count(DISTINCT request_timestamp) AS snaps,
                   max(occupied_bays) AS day_max,
                   stddev_pop(occupied_bays) AS day_sd
            FROM parking WHERE node_type='level' GROUP BY 1, 2, 3
        ),
        base AS (
            SELECT garage, level, median(day_max) AS typ_max, avg(day_sd) AS typ_sd
            FROM lvl GROUP BY 1, 2
        )
        SELECT l.garage, l.level, l.day, l.day_max, l.day_sd, b.typ_max, b.typ_sd
        FROM lvl l JOIN base b USING (garage, level)
        WHERE l.snaps >= ? AND b.typ_max > ?
          AND ( l.day_max = 0
             OR (l.day_sd = 0 AND b.typ_sd > 1)
             OR (l.day_max < ? * b.typ_max) )
        ORDER BY l.day
        """,
        [min_full, MIN_TYP_LEVEL_MAX, LEVEL_REDUCED_RATIO],
    ).df()
    for _, r in lvl.iterrows():
        if r["day_max"] == 0:
            mode, severity = "emptied", 1.0
        elif r["day_sd"] == 0 and r["typ_sd"] > 1:
            mode, severity = "frozen sensor", 0.8
        else:
            mode, severity = "far below normal", round(1 - r["day_max"] / r["typ_max"], 2)
        records.append(
            {
                "date": r["day"], "garage": r["garage"], "level": r["level"],
                "type": f"Level {mode}",
                "severity": severity,
                "detail": f"{r['level']}: peak {int(r['day_max'])} cars vs typical {int(r['typ_max'])}",
            }
        )

    if not records:
        return pd.DataFrame(columns=_COLUMNS)

    df = pd.DataFrame.from_records(records)
    df["date"] = pd.to_datetime(df["date"]).dt.date
    return df.sort_values(["date", "severity"], ascending=[False, False]).reset_index(drop=True)
