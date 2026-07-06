# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Overview

This is a sandbox repo containing independent Python projects. The primary active projects are `gitlab-exec-digest/` and `parking-explorer/`.

## gitlab-exec-digest

A Streamlit app that fetches GitLab Merge Request data and uses **Gemini 3 Flash** (`gemini-3-flash-preview`) to generate executive-facing digests and team demo recommendations.

### Running the App

```bash
cd gitlab-exec-digest
poetry install      # first time / after dependency changes
poetry run streamlit run app.py
```

### Environment Setup

Requires a `.env` file in `gitlab-exec-digest/` with:
- `GITLAB_URL` — GitLab instance URL
- `GITLAB_TOKEN` — Personal access token
- `COMPANY_GROUP_ID` — GitLab group ID to scope project fetching (optional; falls back to all membership projects)
- `GEMINI_API_KEY` — Google Gemini API key

### Architecture

**`app.py`** — Entry point. Manages the Streamlit sidebar (repo filtering, timeframe selection, fetch trigger) and renders the three main tabs by delegating to `tabs.py`. Imports from `gitlab_data` only.

**`gitlab_data.py`** — GitLab data layer:
- `get_gitlab_client()` / `fetch_all_projects()` — cached GitLab connection and project map (`path_with_namespace → id`)
- `fetch_merge_requests()` — fetches merged MRs in parallel (8 threads via `ThreadPoolExecutor`), filters out Renovate bot, and collects diffs. Cached for 5 minutes.
- `get_date_range()` — resolves a timeframe label (e.g. "Last Full Day") into ISO 8601 start/end strings

**`gemini.py`** — Gemini LLM layer:
- `_DIGEST_SCHEMA` / `_SNITCH_SCHEMA` — `types.Schema` definitions for constrained JSON decoding
- `_build_mr_context()` — shared helper that formats MR list into a prompt-ready context string
- `summarize_with_gemini()` — sends MR data to Gemini and returns structured JSON with `executive_summary`, `impactful_changes`, and `technical_highlights`
- `auto_snitch_with_gemini()` — sends MR data to Gemini and returns a JSON list of demo-worthy MRs with song recommendations

**`tabs.py`** — Three `@st.fragment` renderers. Imports from `gemini` only.
- `render_team_stats_tab` — Altair charts: top authors, top repos, top reviewers, cycle time histogram, merges by day of week
- `render_digest_tab` — Triggers `summarize_with_gemini`, renders the structured executive digest, provides Markdown download
- `render_snitch_tab` — Triggers `auto_snitch_with_gemini`, renders demo recommendations with song pairings

### Key Patterns

- LLM results are stored in `st.session_state` (`digest_result`, `snitch_result`) so re-renders don't re-call Gemini
- Fetching new MR data clears stale LLM results from session state
- Project list is cached for 1 hour (`ttl=3600`); MR data for 5 minutes (`ttl=300`)

## parking-explorer

A Streamlit app that explores Franklin, TN parking-garage availability collected in DynamoDB (`franklin_parking_api_data`, us-east-2) every 5 minutes. Snapshots are synced into a local **DuckDB** cache and explored offline — the app never scans DynamoDB.

### Running the App

```bash
cd parking-explorer
poetry install                    # first time / after dependency changes
poetry run python sync_cli.py     # sync DynamoDB -> local DuckDB (first run backfills)
poetry run streamlit run app.py
poetry run pytest                 # flatten/store unit tests + headless app smoke tests
```

Requires Python 3.13 (`poetry env use python3.13`).

### Environment Setup

AWS credentials come from the standard AWS chain (env vars, `~/.aws/credentials`, or an SSO profile), **not** `.env`. Optional `.env` (see `.env.example`) overrides:
- `AWS_REGION` (default `us-east-2`)
- `PARKING_TABLE_NAME` (default `franklin_parking_api_data`)
- `PARKING_TZ` (default `America/Chicago`) — timezone for all time-of-day / day-of-week analysis
- `PARKING_START_DATE` (default `2025-08-20`) — drop data before this local date (a ~6-month Lambda outage left early-2025 data sparse); blank keeps everything
- `PARKING_DB_PATH` (default `./parking.duckdb`)

### Architecture

Data flow: DynamoDB → `sync` (flatten) → DuckDB → `app.py` (read-only).

**`parking/config.py`** — env-driven config (region, table, timezone, DB path, start-date cutoff).

**`parking/flatten.py`** — `flatten_response()` turns each item's nested `api_response` tree (system → garage → level → zone) into tidy long rows with derived `available_bays` / `occupancy_pct`. `parse_timestamp()` handles ISO strings (optional trailing `Z`) and converts UTC → local. `COLUMNS` is the schema contract shared with `store.py`.

**`parking/store.py`** — DuckDB layer. Table keyed on `(request_timestamp, path)` with `INSERT … ON CONFLICT DO NOTHING` (idempotent re-sync). `prune_before()` enforces the start-date cutoff; short-lived connections (read-only for the app, read-write for sync).

**`parking/sync.py`** — `sync()` runs an incremental filtered `Scan` (`request_timestamp > last cached`). The table's partition key *is* `request_timestamp`, so it can't be range-queried; the filter still reads server-side, but the win is local (only new snapshots are parsed/stored). First run backfills; every run prunes pre-cutoff rows.

**`parking/anomalies.py`** — `detect()` flags days deviating from each series' own baseline: collection gaps (missing snapshots), suppressed garage peaks (vs the weekday-typical peak), and level outages (a normally-used level emptied / frozen / far below normal).

**`app.py`** — Streamlit dashboard with five tabs (Overview, Patterns, Anomalies, Garage detail, Data). Pushes all aggregation into DuckDB SQL; Altair charts use a colorblind-safe (Okabe-Ito) categorical palette.

### Key Patterns

- The app reads DuckDB only (never DynamoDB); the sidebar **Sync** button (or `sync_cli.py`) refreshes the cache
- Query results are cached via `st.cache_data` keyed on a data "version" (row count + newest timestamp), so a sync busts the cache
- DuckDB aggregation over ~3M rows keeps the UI responsive; tables use `st.column_config` (not `Styler`) to avoid cell-count limits
- `parking.duckdb` is git-ignored (rebuildable from DynamoDB); only code is tracked
