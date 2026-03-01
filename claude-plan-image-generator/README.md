# Claude Plan Image Generator

A small Streamlit app that turns [Claude Code](https://claude.ai/code) plan files into images using Google's Gemini image generation API.

## How it works

Plan files live in `~/.claude/plans/` as markdown files with human-readable slug names (e.g. `cheerful-leaping-clarke`). This app lets you pick a plan and generate a visual representation of it in one of two modes:

- **Title only** — the filename slug is sent directly to the image model as the prompt.
- **Full markdown** — the plan content is first sent to Gemini Flash, which distills it into a concise visual metaphor prompt. A **Title strength** slider controls how much creative weight the filename carries vs. the content.

The image model used is `gemini-3-pro-image-preview`. Generated images can be downloaded as PNG.

## Setup

**Prerequisites:** Python ≥ 3.11, [Poetry](https://python-poetry.org/), a [Google AI API key](https://aistudio.google.com/app/apikey).

```bash
git clone <repo>
cd claude-plan-image-generator

poetry install

cp .env.example .env
# edit .env and set GEMINI_API_KEY=your_key_here
```

## Running

```bash
poetry run streamlit run app.py
```

Then open [http://localhost:8501](http://localhost:8501) in your browser.
