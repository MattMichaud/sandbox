# 🚀 GitLab Executive Engineering Digest

A Streamlit-powered application that leverages **Gemini 3 Flash** to transform raw GitLab Merge Request data into high-level, impactful digests for company executives and engineering leaders.

## 📖 Overview
This tool was designed for engineering leaders to quickly synthesize development velocity and technical wins across multiple repositories. By analyzing MR titles, descriptions, and code diffs, it highlights the "Why" behind the code, rather than just the "What."

## ✨ Features

* **Smart Repository Selection**: Wildcard/pattern matching to quickly filter through complex GitLab sub-group hierarchies.
* **Automated Noise Reduction**: Built-in filters to exclude bot activity (e.g., Renovate) and focus on human-driven impact.
* **Parallel Fetching**: MR data is fetched concurrently across repos (8 threads) for faster load times.
* **Flexible Timeframes**: Choose between rolling windows (last 24 hours / 7 days / 30 days) or calendar-bounded "Full" periods (last full day / week / month) that cap at midnight.

### Tab 1 — Team Stats
A behavioral dashboard with six Altair charts:
- Top authors and top repositories by MR count
- Top reviewers by MRs reviewed
- Cycle time distribution (hours from open to merge)
- Most discussed MRs by comment count
- Merge throughput by day of week

### Tab 2 — Executive Digest
LLM-powered summary (via `gemini-3-flash-preview`, temperature 0.2) that produces:
- **Executive Summary**: 1–2 sentence velocity overview
- **Impactful Changes**: Up to 5 business-value-focused highlights with author, context area, and direct MR link
- **Technical Highlights**: Up to 10 engineering-detail callouts (architecture, refactors, library updates)
- Download the full digest as a Markdown file

### Tab 3 — Auto Snitch Tool
Identifies the most demo-worthy MRs for your weekly eng meeting. For each recommendation:
- Demo title, author, and description
- Song recommendation that loosely matches the content

LLM results in both Tab 2 and Tab 3 are persisted in session state and cleared automatically when new MR data is fetched.

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
COMPANY_GROUP_ID=12345        # optional; scopes project list to a GitLab group
GEMINI_API_KEY=your_gemini_api_key
```

`COMPANY_GROUP_ID` is optional. If omitted, the app fetches all projects you're a member of.

### Run
```bash
poetry run streamlit run app.py
```
