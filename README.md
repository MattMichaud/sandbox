# sandbox

A collection of independent personal projects.

## Projects

### [`gitlab-exec-digest/`](gitlab-exec-digest/)
A Streamlit app that fetches GitLab Merge Request data and uses Gemini to generate executive-facing digests and team demo recommendations. Features parallel MR fetching, structured JSON output, Altair charts, and Markdown export.

### [`claude-plan-image-generator/`](claude-plan-image-generator/)
A Streamlit app that turns [Claude Code](https://claude.ai/code) plan files into images using Gemini's image generation API. Supports two modes: generating from the plan's filename slug alone, or distilling the full plan markdown into a visual metaphor prompt first.

### [`variation_generation/`](variation_generation/)
A Python script that reads a template text file with bracketed variation syntax (`[[option1||option2]]`) and generates a CSV of all possible permutations.

### [`wordle_solver/`](wordle_solver/)
A command-line Wordle solver that ranks candidate words by expected eliminations using letter frequency analysis.

### [`get_models.py`](get_models.py)
A quick utility script to list all Gemini models available for your API key.
