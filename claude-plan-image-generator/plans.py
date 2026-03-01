from datetime import datetime, timedelta
from pathlib import Path

import streamlit as st

PLANS_DIR = Path.home() / ".claude" / "plans"


@st.cache_data
def list_plans() -> list[str]:
    if not PLANS_DIR.exists():
        return []
    files = [p for p in PLANS_DIR.iterdir() if p.is_file()]
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return [p.name for p in files]


def extract_plan_title(plan_name: str) -> str:
    """Return the first # heading from the plan file, or a formatted slug fallback."""
    try:
        for line in (PLANS_DIR / plan_name).read_text().splitlines():
            if line.startswith("# "):
                return line[2:].strip()
    except Exception:
        pass
    return plan_name.replace("-", " ").title()


def format_plan_option(plan_name: str) -> str:
    """Format a plan as 'Title  ·  <human date>' for the selectbox."""
    mtime = datetime.fromtimestamp((PLANS_DIR / plan_name).stat().st_mtime)
    now = datetime.now()
    if mtime.date() == now.date():
        date_str = f"Today at {mtime.strftime('%-I:%M %p')}"
    elif mtime.date() == (now - timedelta(days=1)).date():
        date_str = f"Yesterday at {mtime.strftime('%-I:%M %p')}"
    elif mtime.year == now.year:
        date_str = mtime.strftime("%-d %b at %-I:%M %p")
    else:
        date_str = mtime.strftime("%-d %b %Y")
    return f"{extract_plan_title(plan_name)}  ·  {date_str}"
