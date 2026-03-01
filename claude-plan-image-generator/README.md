# Claude Plan Image Generator

A Streamlit app that turns [Claude Code](https://claude.ai/code) plan files into images using Google's Gemini API.

## How it works

Plan files live in `~/.claude/plans/` as markdown files with human-readable slug names (e.g. `cheerful-leaping-clarke.md`). The app has two tabs:

### Generate tab

Pick a plan and configure generation options, then click **Generate**:

**Artistic style** (optional) — choose a style from a configurable list (e.g. Watercolor painting, Pixel art, Cyberpunk) or leave it as "No style (default)". Applies to both generation modes.

**Image source** — two modes:

- **Title only** — the filename slug (dashes replaced with spaces, `.md` stripped) is sent directly to the image model. If a style is selected, the prompt becomes e.g. `"cheerful leaping clarke in the style of a Watercolor painting"`.
- **Full markdown** — the plan content is first sent to Gemini Flash, which distills it into a concise visual metaphor prompt (max 150 words). Two additional controls appear:
  - **Title strength** — `Low / Medium / High` slider controlling how much creative weight the filename carries vs. the content.
  - The selected artistic style, if any, is injected as a hard constraint into the distillation instruction.

After generation the image is shown with its prompt (expandable), a **Download PNG** button, and a **Publish to Gallery** button. Publishing saves the image and its metadata (plan name, prompt, mode, style) to a local `gallery/` directory, shows a confirmation toast, and refreshes the Gallery tab in the background.

### Gallery tab

Displays all published images in a 2-column grid, newest first. Each card shows:
- The image (click to open full-size lightbox, click again to dismiss)
- Bold plan title
- Caption: `plan-filename  ·  Title only/Full markdown  ·  Style` (style omitted when none)
- Expandable **Image prompt** section
- **Delete** button

The gallery persists across app restarts. The `gallery/` directory is excluded from Git.

## Customising styles

Edit `styles.toml` in the project root to add, remove, or reorder artistic styles. The file is plain TOML and is reloaded on app restart:

```toml
styles = [
    "Watercolor painting",
    "Oil painting",
    "Pencil sketch",
    # ...
]
```

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

Then open [http://localhost:8501](http://localhost:8501) in your browser. The app opens in wide mode by default.

## Architecture

| File | Role |
|------|------|
| `app.py` | Entry point — page config, API key check, `st.tabs` layout |
| `tabs.py` | `@st.fragment` renderers for the Generate and Gallery tabs |
| `gallery.py` | Persistence layer — save, load, delete gallery entries; `gallery/metadata.json` manifest |
| `gemini.py` | Gemini API calls — `markdown_to_image_prompt()` and `generate_image()` |
| `plans.py` | Plan file utilities — `list_plans()`, `extract_plan_title()`, `load_styles()` |
| `styles.toml` | User-editable list of artistic styles |

Models used:
- **Image generation:** `gemini-3-pro-image-preview`
- **Prompt distillation (Full markdown):** `gemini-3-flash-preview`
