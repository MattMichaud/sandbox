# Franklin Parking Explorer

Explore and visualize the Franklin parking-availability data collected in
DynamoDB every 5 minutes. Snapshots are synced into a **local DuckDB cache**
once, and a **Streamlit** app explores that cache — so the UI never scans
DynamoDB and stays fast over millions of rows.

## Architecture

```
DynamoDB (franklin_parking_api_data, us-east-2)
   │  incremental filtered Scan (request_timestamp > last synced)
   ▼
parking/sync.py ──flatten──► DuckDB (parking.duckdb)  ◄── app.py (Streamlit, read-only)
```

- **`parking/flatten.py`** — turns each item's nested `api_response` tree
  (system → garage → level → zone) into tidy long rows with derived
  `available_bays` / `occupancy_pct`, and parses timestamps (UTC → local tz).
- **`parking/store.py`** — DuckDB schema + idempotent insert. Primary key
  `(request_timestamp, path)` makes re-syncs safe (`ON CONFLICT DO NOTHING`).
- **`parking/sync.py`** — pulls only snapshots newer than what's cached. The
  first run backfills the whole table; later runs fetch just the new rows.
- **`parking/anomalies.py`** — flags days that deviate from each series' own
  baseline: collection gaps (missing snapshots), suppressed garage peaks (vs the
  weekday norm), and level outages (a normally-used level emptied, frozen, or far
  below normal while capacity is unchanged).
- **`app.py`** — Streamlit dashboard (Overview, Patterns, Anomalies, Garage
  detail, Data).

### Why a local cache?

The table's partition key *is* `request_timestamp`, so it can't be
range-queried; incremental sync uses a filtered `Scan`. The filter runs
server-side, so RCU cost doesn't shrink — but the app-side win is large: only
*new* snapshots are parsed/stored, and exploration reads DuckDB, not DynamoDB.

> **Scaling later:** to make syncs cheap on the DynamoDB side too, add a GSI
> (`gsi_pk` bucket key + `request_timestamp` sort key) and switch the scan to a
> `Query`. That needs a one-line Lambda change + a one-time attribute backfill —
> deferred for now since a full filtered scan costs ~pennies at this size.

## Setup

```bash
cd parking-explorer
poetry install
cp .env.example .env        # adjust region / table / timezone if needed
```

AWS credentials come from your normal AWS config (env vars, `~/.aws/credentials`,
or an SSO profile) — not from `.env`.

## Usage

```bash
# 1. Pull new snapshots into the local DuckDB cache (first run backfills everything)
poetry run python sync_cli.py

# 2. Explore
poetry run streamlit run app.py
```

You can also click **🔄 Sync new data** in the app's sidebar instead of the CLI.

## Tests

```bash
poetry run pytest          # flattener unit tests + a headless full-app smoke test
```

The smoke test runs the entire Streamlit script against the local cache and is
skipped automatically when no data has been synced yet.

## Configuration (`.env`)

| Variable | Default | Purpose |
|---|---|---|
| `AWS_REGION` | `us-east-2` | DynamoDB region |
| `PARKING_TABLE_NAME` | `franklin_parking_api_data` | Source table |
| `PARKING_TZ` | `America/Chicago` | Timezone for all time-of-day analysis |
| `PARKING_START_DATE` | `2025-08-20` | Drop data before this local date (a Lambda outage left a gap in early-2025 data). Pruned on sync and never re-downloaded; set empty to keep all. |
| `PARKING_DB_PATH` | `./parking.duckdb` | Local cache file location |
