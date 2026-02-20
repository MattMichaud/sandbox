# 🚀 GitLab Executive Engineering Digest

A Streamlit-powered application that leverages **Gemini 3 Flash** to transform raw GitLab Merge Request data into high-level, impactful digests for company executives.

## 📖 Overview
This tool was designed for engineering leaders to quickly synthesize development velocity and technical wins across multiple repositories. By analyzing MR titles, descriptions, and code diffs, it highlights the "Why" behind the code, rather than just the "What."

## ✨ Features
* **Smart Repository Selection**: Wildcard/Pattern matching to quickly filter through complex GitLab sub-group hierarchies.
* **Automated Noise Reduction**: Built-in filters to exclude bot activity (e.g., Renovate) and focus on human-driven impact.
* **LLM-Powered Analysis**: Uses `gemini-3-flash-preview` with a low temperature (0.2) for consistent, deterministic technical summaries.
* **Timeframe Filtering**: Quickly toggle between daily, weekly, or monthly views.
* **Executive-Ready Exports**: Download the generated summary as a clean Markdown file.