"""Franklin Parking Explorer — Streamlit front-end over the local DuckDB cache.

Reads only from DuckDB (never scans DynamoDB). The sidebar "Sync" button pulls
new snapshots via parking.sync. All aggregation is pushed into DuckDB SQL so the
UI stays responsive over ~1.5M rows.
"""

from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

import altair as alt
import pandas as pd
import streamlit as st

from parking import anomalies, store
from parking.config import DB_PATH, LOCAL_TZ, TABLE_NAME
from parking.sync import sync

st.set_page_config(page_title="Franklin Parking Explorer", page_icon="🅿️", layout="wide")

# Okabe-Ito: canonical colorblind-safe categorical palette, assigned in fixed
# order (never cycled). Garages get a stable identity color regardless of filters.
GARAGE_COLORS = ["#0072B2", "#E69F00", "#009E73", "#CC79A7", "#D55E00", "#56B4E9"]
WEEKDAY_COLOR, WEEKEND_COLOR = "#0072B2", "#E69F00"
DOW_ORDER = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
# Per-day line colors (Okabe-Ito; pale yellow dropped — too faint for a line).
DOW_COLORS = {
    "Monday": "#0072B2",     # blue
    "Tuesday": "#009E73",    # bluish green
    "Wednesday": "#D55E00",  # vermillion
    "Thursday": "#CC79A7",   # reddish purple
    "Friday": "#E69F00",     # orange
    "Saturday": "#56B4E9",   # sky blue
    "Sunday": "#000000",     # black
}
FLOW_IN_COLOR, FLOW_OUT_COLOR = "#0072B2", "#D55E00"


def _humanize_age(td: dt.timedelta) -> str:
    """Compact human-readable age, e.g. '12 min', '3h 5m', '2d 4h'."""
    mins = int(td.total_seconds() // 60)
    if mins < 60:
        return f"{mins} min"
    if mins < 60 * 24:
        return f"{mins // 60}h {mins % 60}m"
    return f"{mins // (60 * 24)}d {(mins // 60) % 24}h"


# --------------------------------------------------------------------------- #
# Data access: short-lived read-only connections, results cached and keyed on a
# data "version" (row count + newest timestamp) so a sync busts the cache.
# --------------------------------------------------------------------------- #
def data_version() -> tuple:
    if not DB_PATH.exists():
        return (0, None)
    con = store.connect(read_only=True)
    try:
        return (store.row_count(con), store.get_last_timestamp(con))
    finally:
        con.close()


@st.cache_data(ttl=300, show_spinner=False)
def q(sql: str, params: tuple, version: tuple) -> pd.DataFrame:
    con = store.connect(read_only=True)
    try:
        return con.execute(sql, list(params)).df()
    finally:
        con.close()


@st.cache_data(ttl=300, show_spinner=False)
def get_anomalies(version: tuple) -> pd.DataFrame:
    con = store.connect(read_only=True)
    try:
        return anomalies.detect(con)
    finally:
        con.close()


def in_clause(garages: list[str]) -> tuple[str, tuple]:
    """Build an ``IN (?, ?, …)`` fragment + params for a garage list."""
    placeholders = ",".join(["?"] * len(garages))
    return f"({placeholders})", tuple(garages)


def run_sync() -> None:
    with st.spinner("Scanning DynamoDB for new snapshots…"):
        result = sync()
    st.cache_data.clear()
    if result["new_items"]:
        st.toast(
            f"Synced {result['new_items']:,} new snapshots "
            f"({result['rows_inserted']:,} rows).",
            icon="✅",
        )
    else:
        st.toast("Already up to date.", icon="✅")


# --------------------------------------------------------------------------- #
# Empty-state onboarding
# --------------------------------------------------------------------------- #
version = data_version()
if version[0] == 0:
    st.title("🅿️ Franklin Parking Explorer")
    st.info(
        f"No local data yet. Click below to pull snapshots from `{TABLE_NAME}` "
        "into the local DuckDB cache (the first sync scans the whole table)."
    )
    if st.button("🔄 Sync from DynamoDB", type="primary"):
        run_sync()
        st.rerun()
    st.stop()


# --------------------------------------------------------------------------- #
# Sidebar: sync + filters
# --------------------------------------------------------------------------- #
bounds = q(
    "SELECT min(ts_local)::DATE, max(ts_local)::DATE, max(ts_local) FROM parking",
    (),
    version,
)
min_date, max_date, latest_ts = bounds.iloc[0]

all_garages = q(
    "SELECT DISTINCT garage FROM parking WHERE node_type='garage' ORDER BY garage",
    (),
    version,
)["garage"].tolist()

with st.sidebar:
    st.header("🅿️ Parking Explorer")
    if st.button("🔄 Sync new data", use_container_width=True):
        run_sync()
        st.rerun()
    st.caption(
        f"Latest snapshot: **{pd.Timestamp(latest_ts):%b %-d, %Y %-I:%M %p}**  \n"
        f"{version[0]:,} rows cached"
    )
    st.divider()

    selected_garages = st.multiselect("Garages", all_garages, default=all_garages)

    default_start = max(min_date, max_date - dt.timedelta(days=28))
    date_range = st.date_input(
        "Date range",
        value=(default_start, max_date),
        min_value=min_date,
        max_value=max_date,
    )
    if isinstance(date_range, tuple) and len(date_range) == 2:
        start_date, end_date = date_range
    else:  # user mid-selection (single date picked)
        start_date = end_date = date_range if isinstance(date_range, dt.date) else min_date

if not selected_garages:
    st.warning("Select at least one garage in the sidebar.")
    st.stop()

# Shared filter fragments. end is exclusive → add a day so the end date is inclusive.
g_clause, g_params = in_clause(selected_garages)
date_params = (start_date, end_date + dt.timedelta(days=1))
where = f"node_type='garage' AND ts_local >= ? AND ts_local < ? AND garage IN {g_clause}"
base_params = date_params + g_params

st.title("🅿️ Franklin Parking Explorer")

# Freshness banner. The cache is only as current as the last sync; if it stays
# stale right after a sync, the upstream collector/Lambda is likely down.
_age = dt.datetime.now(ZoneInfo(LOCAL_TZ)).replace(tzinfo=None) - pd.Timestamp(latest_ts).to_pydatetime()
if _age > dt.timedelta(days=1):
    st.error(
        f"⚠️ Data is stale — newest snapshot is **{_humanize_age(_age)}** old "
        f"({pd.Timestamp(latest_ts):%b %-d, %Y · %-I:%M %p}). Click **Sync new data** in the "
        "sidebar; if it stays stale, the collector/Lambda may be down."
    )
elif _age > dt.timedelta(minutes=30):
    st.warning(
        f"⚠️ Cached data is **{_humanize_age(_age)}** old "
        f"({pd.Timestamp(latest_ts):%-I:%M %p}) — snapshots arrive every 5 min. "
        "**Sync new data** to refresh."
    )

tab_overview, tab_patterns, tab_anomalies, tab_drill, tab_data = st.tabs(
    ["Overview", "Patterns", "Anomalies", "Garage detail", "Data"]
)


# --------------------------------------------------------------------------- #
# Overview: current status KPIs + occupancy over time
# --------------------------------------------------------------------------- #
with tab_overview:
    latest = q(
        """
        WITH last2 AS (
            SELECT DISTINCT request_timestamp FROM parking
            ORDER BY request_timestamp DESC LIMIT 2
        )
        SELECT p.request_timestamp, p.garage, p.available_bays, p.total_bays,
               p.occupancy_pct
        FROM parking p JOIN last2 USING (request_timestamp)
        WHERE p.node_type='garage'
        ORDER BY p.request_timestamp DESC, p.garage
        """,
        (),
        version,
    )

    st.subheader("Right now")
    st.caption("Available bays at the latest snapshot (Δ vs the previous 5-min reading).")
    ts_sorted = sorted(latest["request_timestamp"].unique(), reverse=True)
    cur = latest[latest["request_timestamp"] == ts_sorted[0]].set_index("garage")
    prev = (
        latest[latest["request_timestamp"] == ts_sorted[1]].set_index("garage")
        if len(ts_sorted) > 1
        else None
    )

    shown = [g for g in all_garages if g in cur.index]
    cols = st.columns(len(shown) + 1)
    for col, g in zip(cols, shown):
        avail = int(cur.loc[g, "available_bays"])
        occ = cur.loc[g, "occupancy_pct"]
        delta = (
            int(avail - prev.loc[g, "available_bays"])
            if prev is not None and g in prev.index
            else None
        )
        col.metric(
            f"{g}",
            f"{avail:,} free",
            delta=None if delta is None else f"{delta:+d}",
            help=f"{occ:.0f}% full · {int(cur.loc[g, 'total_bays']):,} total bays",
        )
    total_avail = int(cur["available_bays"].sum())
    total_prev = int(prev["available_bays"].sum()) if prev is not None else None
    cols[-1].metric(
        "All selected",
        f"{cur.loc[shown, 'available_bays'].sum():,.0f} free",
        delta=None if total_prev is None else f"{total_avail - total_prev:+d}",
    )

    st.divider()
    st.subheader("Occupancy over time")
    ts_df = q(
        f"""
        SELECT date_trunc('hour', ts_local) AS hour, garage,
               avg(occupancy_pct) AS occupancy_pct,
               avg(available_bays) AS available_bays
        FROM parking WHERE {where}
        GROUP BY 1, 2 ORDER BY 1
        """,
        base_params,
        version,
    )
    if ts_df.empty:
        st.info("No data in the selected range.")
    else:
        color = alt.Color(
            "garage:N",
            scale=alt.Scale(domain=all_garages, range=GARAGE_COLORS[: len(all_garages)]),
            legend=alt.Legend(title=None, orient="top"),
        )
        line = (
            alt.Chart(ts_df)
            .mark_line(strokeWidth=2)
            .encode(
                x=alt.X("hour:T", title=None),
                y=alt.Y(
                    "occupancy_pct:Q",
                    title="Occupancy %",
                    scale=alt.Scale(domain=[0, 100]),
                ),
                color=color,
                tooltip=[
                    alt.Tooltip("hour:T", title="Hour"),
                    alt.Tooltip("garage:N", title="Garage"),
                    alt.Tooltip("occupancy_pct:Q", title="Occupancy %", format=".0f"),
                    alt.Tooltip("available_bays:Q", title="Avg free", format=".0f"),
                ],
            )
            .properties(height=360)
        )
        st.altair_chart(line, use_container_width=True)

    st.divider()
    st.subheader("Daily peak occupancy calendar")
    st.caption(
        "Each cell is one day (rows = months, columns = day of month), shaded by that day's "
        "peak occupancy across selected garages. Full history — ignores the date slider."
    )
    cal = q(
        f"""
        WITH snap AS (
            SELECT request_timestamp, ts_local::DATE AS day,
                   100.0 * sum(occupied_bays) / nullif(sum(total_bays), 0) AS occ
            FROM parking WHERE node_type='garage' AND garage IN {g_clause}
            GROUP BY request_timestamp, day
        )
        SELECT day, max(occ) AS peak, avg(occ) AS avg_occ
        FROM snap GROUP BY day ORDER BY day
        """,
        g_params,
        version,
    )
    if cal.empty:
        st.info("No data.")
    else:
        cal["day"] = pd.to_datetime(cal["day"])
        cal["month"] = cal["day"].dt.strftime("%b %Y")
        cal["dom"] = cal["day"].dt.day
        month_order = cal.sort_values("day")["month"].drop_duplicates().tolist()
        calendar = (
            alt.Chart(cal)
            .mark_rect(stroke="white", strokeWidth=1)
            .encode(
                x=alt.X("dom:O", title="Day of month"),
                y=alt.Y("month:N", sort=month_order, title=None),
                color=alt.Color(
                    "peak:Q",
                    scale=alt.Scale(scheme="reds", domain=[0, 100]),
                    legend=alt.Legend(title="Daily peak %"),
                ),
                tooltip=[
                    alt.Tooltip("day:T", title="Date"),
                    alt.Tooltip("peak:Q", title="Peak %", format=".0f"),
                    alt.Tooltip("avg_occ:Q", title="Avg %", format=".0f"),
                ],
            )
            .properties(height=alt.Step(22))
        )
        st.altair_chart(calendar, use_container_width=True)


# --------------------------------------------------------------------------- #
# Patterns: hour × weekday heatmap, typical-day spread band, net flow
# --------------------------------------------------------------------------- #
with tab_patterns:
    st.subheader("When is it full?")
    st.caption(
        "Average occupancy by hour and weekday, capacity-weighted across the "
        "selected garages. Darker = fuller."
    )
    heat = q(
        f"""
        SELECT dayname(ts_local) AS dow, hour(ts_local) AS hr,
               100.0 * sum(occupied_bays) / nullif(sum(total_bays), 0) AS occupancy_pct
        FROM parking WHERE {where}
        GROUP BY 1, 2
        """,
        base_params,
        version,
    )
    if heat.empty:
        st.info("No data in the selected range.")
    else:
        heatmap = (
            alt.Chart(heat)
            .mark_rect(stroke="white", strokeWidth=1)  # 2px surface gap between cells
            .encode(
                x=alt.X("hr:O", title="Hour of day"),
                y=alt.Y("dow:O", sort=DOW_ORDER, title=None),
                color=alt.Color(
                    "occupancy_pct:Q",
                    scale=alt.Scale(scheme="reds", domain=[0, 100]),
                    legend=alt.Legend(title="Occupancy %"),
                ),
                tooltip=[
                    alt.Tooltip("dow:N", title="Day"),
                    alt.Tooltip("hr:O", title="Hour"),
                    alt.Tooltip("occupancy_pct:Q", title="Occupancy %", format=".0f"),
                ],
            )
            .properties(height=280)
        )
        st.altair_chart(heatmap, use_container_width=True)

    st.divider()
    st.subheader("Typical day")
    mode = st.segmented_control(
        "Compare",
        ["Weekday vs weekend", "Specific days"],
        default="Weekday vs weekend",
        label_visibility="collapsed",
        key="typical_day_mode",
    )

    curve, domain, color_range = None, None, None
    if mode == "Specific days":
        picked = st.multiselect(
            "Days of week",
            DOW_ORDER,
            default=["Monday", "Friday"],
            key="typical_day_picks",
        )
        picked = [d for d in DOW_ORDER if d in picked]  # stable weekly order
        if not picked:
            st.info("Pick at least one day of week to compare.")
        else:
            day_ph = ",".join(["?"] * len(picked))
            curve = q(
                f"""
                WITH snap AS (
                    SELECT request_timestamp, hour(ts_local) AS hr,
                           dayname(ts_local) AS day_type,
                           100.0 * sum(occupied_bays) / nullif(sum(total_bays), 0) AS occ
                    FROM parking WHERE {where} AND dayname(ts_local) IN ({day_ph})
                    GROUP BY request_timestamp, hr, day_type
                )
                SELECT hr, day_type, median(occ) AS med,
                       quantile_cont(occ, 0.1) AS lo, quantile_cont(occ, 0.9) AS hi
                FROM snap GROUP BY hr, day_type ORDER BY hr
                """,
                base_params + tuple(picked),
                version,
            )
            domain, color_range = picked, [DOW_COLORS[d] for d in picked]
    else:
        curve = q(
            f"""
            WITH snap AS (
                SELECT request_timestamp, hour(ts_local) AS hr,
                       CASE WHEN dayofweek(ts_local) IN (0, 6) THEN 'Weekend'
                            ELSE 'Weekday' END AS day_type,
                       100.0 * sum(occupied_bays) / nullif(sum(total_bays), 0) AS occ
                FROM parking WHERE {where}
                GROUP BY request_timestamp, hr, day_type
            )
            SELECT hr, day_type, median(occ) AS med,
                   quantile_cont(occ, 0.1) AS lo, quantile_cont(occ, 0.9) AS hi
            FROM snap GROUP BY hr, day_type ORDER BY hr
            """,
            base_params,
            version,
        )
        domain, color_range = ["Weekday", "Weekend"], [WEEKDAY_COLOR, WEEKEND_COLOR]

    if curve is None:
        pass  # no days selected — message already shown
    elif curve.empty:
        st.info("No data in the selected range.")
    else:
        # A p10–p90 band per series reads clearly for 1–2 series; beyond that the
        # overlapping bands muddy the chart, so fall back to median lines only.
        show_band = curve["day_type"].nunique() <= 2
        st.caption(
            "Median occupancy through the day"
            + (", with a p10–p90 spread band," if show_band else "")
            + " capacity-weighted across selected garages."
            + ("" if show_band else " Spread band hidden with 3+ series to keep the chart readable.")
        )
        day_color = alt.Color(
            "day_type:N",
            scale=alt.Scale(domain=domain, range=color_range),
            legend=alt.Legend(title=None, orient="top"),
        )
        x_enc = alt.X("hr:Q", title="Hour of day", scale=alt.Scale(domain=[0, 23]))
        y_enc = alt.Y("med:Q", title="Occupancy %", scale=alt.Scale(domain=[0, 100]))
        base = alt.Chart(curve)
        layers = []
        if show_band:
            layers.append(
                base.mark_area(opacity=0.2).encode(
                    x=x_enc,
                    y=alt.Y("lo:Q", title="Occupancy %", scale=alt.Scale(domain=[0, 100])),
                    y2="hi:Q",
                    color=day_color,
                )
            )
        layers.append(
            base.mark_line(strokeWidth=2, point=True).encode(
                x=x_enc,
                y=y_enc,
                color=day_color,
                tooltip=[
                    alt.Tooltip("hr:Q", title="Hour"),
                    alt.Tooltip("day_type:N", title=""),
                    alt.Tooltip("med:Q", title="Median %", format=".0f"),
                    alt.Tooltip("lo:Q", title="p10 %", format=".0f"),
                    alt.Tooltip("hi:Q", title="p90 %", format=".0f"),
                ],
            )
        )
        st.altair_chart(alt.layer(*layers).properties(height=320), use_container_width=True)

    st.divider()
    st.subheader("Net flow through the day")
    st.caption(
        "Average net change in parked cars by hour — bars above zero mean the garages "
        "are filling, below zero emptying. Capacity across selected garages."
    )
    flow = q(
        f"""
        WITH snap AS (
            SELECT request_timestamp, ts_local, sum(occupied_bays) AS occ
            FROM parking WHERE {where}
            GROUP BY request_timestamp, ts_local
        ),
        deltas AS (
            SELECT ts_local,
                   occ - lag(occ) OVER (ORDER BY ts_local) AS delta,
                   epoch(ts_local) - epoch(lag(ts_local) OVER (ORDER BY ts_local)) AS gap_s
            FROM snap
        )
        SELECT hour(ts_local) AS hr, avg(delta) * 12 AS net_per_hour
        FROM deltas WHERE gap_s BETWEEN 1 AND 900
        GROUP BY 1 ORDER BY 1
        """,
        base_params,
        version,
    )
    if flow.empty:
        st.info("No data in the selected range.")
    else:
        flow["direction"] = flow["net_per_hour"].ge(0).map({True: "Filling", False: "Emptying"})
        flow_chart = (
            alt.Chart(flow)
            .mark_bar()
            .encode(
                x=alt.X("hr:O", title="Hour of day"),
                y=alt.Y("net_per_hour:Q", title="Avg net change (≈ cars/hour)"),
                color=alt.Color(
                    "direction:N",
                    scale=alt.Scale(
                        domain=["Filling", "Emptying"], range=[FLOW_IN_COLOR, FLOW_OUT_COLOR]
                    ),
                    legend=alt.Legend(title=None, orient="top"),
                ),
                tooltip=[
                    alt.Tooltip("hr:O", title="Hour"),
                    alt.Tooltip("net_per_hour:Q", title="Net cars/hour", format="+.0f"),
                ],
            )
            .properties(height=300)
        )
        st.altair_chart(flow_chart, use_container_width=True)


# --------------------------------------------------------------------------- #
# Anomalies: flag days that deviate from each series' own baseline
# --------------------------------------------------------------------------- #
with tab_anomalies:
    st.subheader("Detected anomalies")
    st.caption(
        "Flags days that deviate from each series' own baseline. Scans the full "
        "history and respects the garage filter, but ignores the date slider."
    )
    with st.expander("What do these anomaly types mean?"):
        st.markdown(
            """
Each detector compares a day against **that same series' own history**, so the
threshold adapts per garage and per level.

- **Collection gap** — the day logged far fewer than a normal day's ~288
  five-minute snapshots. Points to a *data-pipeline* interruption (the collector
  or source API losing power/connectivity), not a parking pattern.
- **Suppressed activity** — a garage's *peak* occupancy came in far below its
  typical peak for that weekday. Signals a demand collapse across the whole
  garage (e.g. a snowstorm keeping everyone home).
- **Level emptied** — a normally-used level sat at **zero** cars all day while
  its capacity was unchanged — the hallmark of a level closed off (construction,
  an event, a blockage).
- **Level frozen sensor** — a level reported the *exact same* count all day (no
  variation) even though it normally fluctuates — a stuck/faulty counter rather
  than real behavior.
- **Level far below normal** — a level's peak was a small fraction of its own
  typical peak (but not fully zero) — a partial closure or a level running well
  under its usual load.

**Severity** is a 0–1 score — higher means further from that series' own normal.
It's set differently per type:

| Type | How severity is computed |
|---|---|
| Collection gap | fraction of the day's ~288 snapshots that are **missing** |
| Suppressed activity | how far the peak fell below the weekday-typical peak (`1 − peak ÷ typical`) |
| Level far below normal | how far the level's peak fell below its own norm (`1 − peak ÷ typical`) |
| Level emptied | fixed **1.0** — can't be emptier than zero |
| Level frozen sensor | fixed **0.8** — a stuck counter has no natural magnitude |

It's a rough ranking heuristic (not a rigorous statistic): its job is to sort the
table and drive the severity slider.
"""
        )
    anoms = get_anomalies(version)
    anoms = anoms[anoms["garage"].isin(selected_garages) | (anoms["garage"] == "All")]

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Anomaly records", f"{len(anoms):,}")
    m2.metric("Collection gaps", int((anoms["type"] == "Collection gap").sum()))
    m3.metric("Suppressed days", int((anoms["type"] == "Suppressed activity").sum()))
    m4.metric("Level outages", int(anoms["type"].str.startswith("Level").sum()))

    # Daily peak occupancy over full history, with suppressed days marked.
    peaks = q(
        f"SELECT ts_local::DATE AS day, garage, max(occupancy_pct) AS peak "
        f"FROM parking WHERE node_type='garage' AND garage IN {g_clause} "
        f"GROUP BY 1, 2 ORDER BY 1",
        g_params,
        version,
    )
    if not peaks.empty:
        peaks["day"] = pd.to_datetime(peaks["day"])
        line = (
            alt.Chart(peaks)
            .mark_line(strokeWidth=1.5, opacity=0.75)
            .encode(
                x=alt.X("day:T", title=None),
                y=alt.Y(
                    "peak:Q",
                    title="Daily peak occupancy %",
                    scale=alt.Scale(domain=[0, 100]),
                ),
                color=alt.Color(
                    "garage:N",
                    scale=alt.Scale(
                        domain=all_garages, range=GARAGE_COLORS[: len(all_garages)]
                    ),
                    legend=alt.Legend(title=None, orient="top"),
                ),
                tooltip=[
                    alt.Tooltip("day:T", title="Date"),
                    alt.Tooltip("garage:N", title="Garage"),
                    alt.Tooltip("peak:Q", title="Peak %", format=".0f"),
                ],
            )
            .properties(height=300)
        )
        layers = [line]
        sup = anoms[anoms["type"] == "Suppressed activity"][["date", "garage"]].copy()
        if not sup.empty:
            sup["day"] = pd.to_datetime(sup["date"])
            sup_pts = peaks.merge(sup[["day", "garage"]], on=["day", "garage"])
            if not sup_pts.empty:
                layers.append(
                    alt.Chart(sup_pts)
                    .mark_point(size=60, filled=True, color="#D55E00")
                    .encode(
                        x="day:T",
                        y="peak:Q",
                        tooltip=[
                            alt.Tooltip("day:T", title="Date"),
                            alt.Tooltip("garage:N", title="Garage"),
                            alt.Tooltip("peak:Q", title="Peak %", format=".0f"),
                        ],
                    )
                )
        st.altair_chart(alt.layer(*layers), use_container_width=True)
        st.caption("Dots = days flagged as suppressed activity (peak far below the weekday norm).")

    st.divider()
    if anoms.empty:
        st.success("No anomalies detected for the selected garages.")
    else:
        types = sorted(anoms["type"].unique())
        fc1, fc2 = st.columns([2, 1])
        picked = fc1.multiselect("Anomaly types", types, default=types)
        min_sev = fc2.slider("Min severity", 0.0, 1.0, 0.0, 0.05)
        view = anoms[anoms["type"].isin(picked) & (anoms["severity"] >= min_sev)]
        st.caption(f"{len(view):,} of {len(anoms):,} records")
        st.dataframe(
            view.rename(
                columns={
                    "date": "Date",
                    "garage": "Garage",
                    "level": "Level",
                    "type": "Type",
                    "severity": "Severity",
                    "detail": "Detail",
                }
            ),
            hide_index=True,
            use_container_width=True,
            height=460,
            column_config={
                "Severity": st.column_config.ProgressColumn(
                    "Severity", min_value=0.0, max_value=1.0, format="%.2f"
                ),
            },
        )


# --------------------------------------------------------------------------- #
# Garage detail: drill into levels for one garage at the latest snapshot
# --------------------------------------------------------------------------- #
with tab_drill:
    garage = st.selectbox("Garage", selected_garages)
    levels = q(
        r"""
        SELECT level, available_bays, occupied_bays, total_bays, occupancy_pct
        FROM parking
        WHERE node_type='level' AND garage = ?
          AND request_timestamp = (SELECT max(request_timestamp) FROM parking)
          AND total_bays > 0
        ORDER BY try_cast(regexp_extract(level, '\d+') AS INTEGER) NULLS LAST, level
        """,
        (garage,),
        version,
    )
    st.subheader(f"{garage} — levels at the latest snapshot")
    if levels.empty:
        st.info("No level breakdown available for this garage.")
    else:
        bars = (
            alt.Chart(levels)
            .mark_bar(cornerRadiusEnd=4, height=alt.RelativeBandSize(0.7))
            .encode(
                x=alt.X("available_bays:Q", title="Available bays"),
                y=alt.Y("level:N", sort=levels["level"].tolist(), title=None),
                color=alt.Color(
                    "occupancy_pct:Q",
                    scale=alt.Scale(scheme="reds", domain=[0, 100]),
                    legend=alt.Legend(title="Occupancy %"),
                ),
                tooltip=[
                    alt.Tooltip("level:N", title="Level"),
                    alt.Tooltip("available_bays:Q", title="Available"),
                    alt.Tooltip("total_bays:Q", title="Total"),
                    alt.Tooltip("occupancy_pct:Q", title="Occupancy %", format=".0f"),
                ],
            )
            .properties(height=max(200, 44 * len(levels)))
        )
        st.altair_chart(bars, use_container_width=True)
        st.dataframe(
            levels.rename(
                columns={
                    "level": "Level",
                    "available_bays": "Available",
                    "occupied_bays": "Occupied",
                    "total_bays": "Total",
                    "occupancy_pct": "Occupancy %",
                }
            ),
            hide_index=True,
            use_container_width=True,
            column_config={
                "Occupancy %": st.column_config.NumberColumn("Occupancy %", format="%.0f"),
            },
        )


# --------------------------------------------------------------------------- #
# Data: aggregated garage-level table + CSV download
# --------------------------------------------------------------------------- #
with tab_data:
    st.subheader("Garage snapshots in range")
    raw = q(
        f"""
        SELECT ts_local, garage, available_bays, occupied_bays, total_bays, occupancy_pct
        FROM parking WHERE {where}
        ORDER BY ts_local DESC, garage
        """,
        base_params,
        version,
    )
    display_cap = 5000
    note = (
        f" — showing the most recent {display_cap:,}; download for all"
        if len(raw) > display_cap
        else ""
    )
    st.caption(f"{len(raw):,} rows in range{note}")
    st.dataframe(
        raw.head(display_cap).rename(
            columns={
                "ts_local": "Timestamp (local)",
                "garage": "Garage",
                "available_bays": "Available",
                "occupied_bays": "Occupied",
                "total_bays": "Total",
                "occupancy_pct": "Occupancy %",
            }
        ),
        hide_index=True,
        use_container_width=True,
        height=460,
        column_config={
            "Timestamp (local)": st.column_config.DatetimeColumn(
                "Timestamp (local)", format="YYYY-MM-DD HH:mm"
            ),
            "Occupancy %": st.column_config.NumberColumn("Occupancy %", format="%.0f"),
        },
    )
    st.download_button(
        "Download CSV",
        raw.to_csv(index=False).encode(),
        file_name="parking_snapshots.csv",
        mime="text/csv",
    )
