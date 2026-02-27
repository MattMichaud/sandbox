# 🚀 GitLab Executive Engineering Digest

A Streamlit-powered application that leverages **Gemini 3 Flash** to transform raw GitLab Merge Request data into high-level, impactful digests for company executives and engineering leaders.

## 📖 Overview
This tool was designed for engineering leaders to quickly synthesize development velocity and technical wins across multiple repositories. By analyzing MR titles, descriptions, and code diffs, it highlights the "Why" behind the code, rather than just the "What."

## ✨ Features

* **Subgroup-Aware Repository Selection**: Two-step picker that mirrors GitLab's group hierarchy. Select one or more teams (any nesting depth) and all repos cascade automatically; optionally filter by name or deselect individual repos. Selecting `(all repos)` includes every repo under the configured group. Falls back to a flat text-filter list when no group is configured.
* **Automated Noise Reduction**: Built-in filters to exclude bot activity (e.g., Renovate) and focus on human-driven impact.
* **Parallel Fetching**: MR data is fetched concurrently across repos (8 threads) for faster load times.
* **Flexible Timeframes**: Calendar-bounded windows (Last Full Day, Last Full Work Week) that cap at midnight, a rolling 30-day window, or a fully custom date range.

### Tab 1 — Team Stats
A behavioral dashboard with six Altair charts:
- Top authors and top repositories by MR count
- Top reviewers by MRs reviewed
- Cycle time distribution (hours from open to merge)
- Most discussed MRs by comment count
- Merge throughput by day of week

### Tab 2 — Executive Digest
LLM-powered summary (via `gemini-3-flash-preview`, temperature 0.2) with schema-enforced JSON output for reliable parsing. Produces:
- **Executive Summary**: 1–2 sentence velocity overview
- **Impactful Changes**: Up to 5 business-value-focused highlights with author, context area, and direct MR link
- **Technical Highlights**: Up to 10 engineering-detail callouts (architecture, refactors, library updates)
- Download the full digest as a Markdown file

### Tab 3 — Auto Snitch Tool
LLM-powered (via `gemini-3-flash-preview`, temperature 0.4) with schema-enforced JSON output. Selects exactly one MR per author and ranks them by demo-worthiness for your weekly technical demo meeting. Scoring prioritizes work that exposes teammates to new techniques or approaches — the goal is inspiration and exposure, not visual polish. For each recommendation:
- Demo title, author, and description (framed around what others can learn from it)
- **Spark Score** (1–10): how likely the MR is to inspire teammates or expose them to a new technique or pattern; cards are sorted highest-to-lowest
- Song recommendation that loosely matches the content
- Authors with no demo-worthy MRs (docs-only, config changes, etc.) are still included with a low spark score rather than omitted

### Tab 4 — Podcast
Generates a two-host conversational podcast from the fetched MR data using Gemini for script generation and Microsoft Edge TTS (`edge-tts`) for free, high-quality neural speech synthesis.

**Controls:**
- **Listener Role**: Engineering Leader, Data & Analytics Leader, Business Leader, or Custom — tailors the language, emphasis, and episode title to the intended audience
- **Podcast Length**: 5 or 10 minutes (word count target scales automatically with speech rate)
- **Speech Rate**: 0–25% speed increase above baseline (default +10%), applied to both TTS synthesis and the word count target

**Output:**
- In-browser audio player with 1×, 1.25×, 1.5× playback speed buttons
- MP3 download
- Expandable transcript showing the full Alex / Matt dialogue

LLM results in Tabs 2, 3, and 4 are persisted in session state and cleared automatically when new MR data is fetched.

## 🗂️ Project Structure

```
gitlab-exec-digest/
├── app.py            # Streamlit entry point — sidebar, tab layout, session state
├── gitlab_data.py    # GitLab data layer — client, project/MR fetching, date utils
├── gemini.py         # Gemini LLM layer — schemas, prompt building, all LLM calls
├── podcast.py        # Audio layer — edge-tts synthesis and MP3 assembly
└── tabs.py           # Tab renderers — Team Stats, Executive Digest, Auto Snitch, Podcast
```

## 🛠️ Setup

### Prerequisites
```
poetry install
```

### Environment Variables
Create a `.env` file in this directory:
```
GITLAB_URL=https://gitlab.example.com
GITLAB_TOKEN=your_personal_access_token
COMPANY_GROUP_ID=12345        # optional; scopes project list and enables subgroup-aware team picker
GEMINI_API_KEY=your_gemini_api_key
```

`COMPANY_GROUP_ID` is optional. If omitted, the app fetches all projects you're a member of.

### Run
```bash
poetry run streamlit run app.py
```
