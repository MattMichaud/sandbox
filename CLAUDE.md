# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Overview

This is a sandbox repo containing independent Python projects. The primary active project is `gitlab-exec-digest/`.

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
