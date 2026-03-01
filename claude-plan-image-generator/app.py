import os
import time
from datetime import datetime, timedelta
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv
from google import genai
from google.genai import types

# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------
load_dotenv()

api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    st.error(
        "GEMINI_API_KEY not found. Copy `.env.example` to `.env` and add your key."
    )
    st.stop()

IMAGE_MODEL = "gemini-3-pro-image-preview"
TEXT_MODEL = "gemini-3-flash-preview"
PLANS_DIR = Path.home() / ".claude" / "plans"

client = genai.Client(api_key=api_key)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
@st.cache_data
def list_plans() -> list[str]:
    if not PLANS_DIR.exists():
        return []
    files = [p for p in PLANS_DIR.iterdir() if p.is_file()]
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return [p.name for p in files]


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


def extract_plan_title(plan_name: str) -> str:
    """Return the first # heading from the plan file, or a formatted slug fallback."""
    try:
        for line in (PLANS_DIR / plan_name).read_text().splitlines():
            if line.startswith("# "):
                return line[2:].strip()
    except Exception:
        pass
    return plan_name.replace("-", " ").title()


def markdown_to_image_prompt(plan_name: str, markdown: str, title_strength: str) -> str:
    strength_instruction = {
        "Low": (
            f"The plan is named '{plan_name}', but treat that as background context only. "
            "Draw your creative inspiration primarily from the content of the plan below."
        ),
        "Medium": (
            f"The plan is named '{plan_name}'. Balance the name and the content equally — "
            "let both inform the visual metaphor."
        ),
        "High": (
            f"The plan is named '{plan_name}'. This name is the primary creative driver. "
            "Let it anchor the image concept; use the content below only as supporting detail."
        ),
    }[title_strength]

    response = client.models.generate_content(
        model=TEXT_MODEL,
        contents=(
            "You are a creative director tasked with visualising a software development plan.\n"
            f"{strength_instruction}\n\n"
            "Write a single, vivid image-generation prompt (max 150 words) that captures the essence "
            "of this plan as a visual metaphor. Focus on mood, theme, and key concepts — not literal "
            "code or text. Output only the prompt, nothing else.\n\n"
            f"{markdown}"
        ),
    )
    return response.text.strip()


def generate_image(prompt: str, status: st.delta_generator.DeltaGenerator) -> bytes:
    """Call the image model with up to 2 retries on 503 errors."""
    delays = [2, 4]
    attempts = len(delays) + 1

    for attempt in range(attempts):
        try:
            response = client.models.generate_content(
                model=IMAGE_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_modalities=["TEXT", "IMAGE"],
                ),
            )
            for part in response.parts:
                if part.inline_data is not None:
                    return part.inline_data.data
            raise ValueError("No image part found in response.")

        except Exception as exc:
            is_503 = "503" in str(exc)
            if is_503 and attempt < len(delays):
                delay = delays[attempt]
                status.update(
                    label=f"Service unavailable — retrying in {delay}s "
                          f"(attempt {attempt + 2}/{attempts})…"
                )
                time.sleep(delay)
                status.update(label=f"Generating image (attempt {attempt + 2}/{attempts})…")
            else:
                raise


# ---------------------------------------------------------------------------
# Main UI
# ---------------------------------------------------------------------------
st.title("Claude Plan Image Generator")

plans = list_plans()

if not plans:
    st.warning(f"No plans found in `{PLANS_DIR}`. Make sure the directory exists and contains plan files.")
    st.stop()

selected_plan = st.selectbox("Select a plan", plans, format_func=format_plan_option)
st.caption(selected_plan)

mode = st.radio("Image source", ["Title only", "Full markdown"], horizontal=True)

title_strength = None
if mode == "Full markdown":
    title_strength = st.select_slider(
        "Title strength",
        options=["Low", "Medium", "High"],
        value="Medium",
        help="How much creative weight to give the plan's filename vs. its content.",
    )

generate = st.button("Generate", type="primary")

if generate:
    if mode == "Title only":
        with st.status("Generating image…") as status:
            try:
                img_bytes = generate_image(selected_plan, status)
                status.update(label="Done!", state="complete")
                st.session_state.img_bytes = img_bytes
                st.session_state.img_caption = selected_plan
                st.session_state.img_filename = f"{selected_plan}.png"
                st.session_state.img_prompt = None
            except Exception as exc:
                status.update(label="Failed", state="error")
                st.error(f"Image generation failed: {exc}")
    else:
        markdown = (PLANS_DIR / selected_plan).read_text()
        try:
            with st.spinner("Step 1/2 — Distilling plan into image prompt…"):
                image_prompt = markdown_to_image_prompt(selected_plan, markdown, title_strength)

            with st.status("Step 2/2 — Generating image…") as status:
                try:
                    img_bytes = generate_image(image_prompt, status)
                    status.update(label="Done!", state="complete")
                    st.session_state.img_bytes = img_bytes
                    st.session_state.img_caption = selected_plan
                    st.session_state.img_filename = f"{selected_plan}.png"
                    st.session_state.img_prompt = image_prompt
                except Exception as exc:
                    status.update(label="Failed", state="error")
                    st.error(f"Image generation failed: {exc}")
        except Exception as exc:
            st.error(f"Failed: {exc}")

if "img_bytes" in st.session_state:
    if st.session_state.img_prompt:
        with st.expander("Generated image prompt", expanded=False):
            st.write(st.session_state.img_prompt)
    st.image(st.session_state.img_bytes, caption=st.session_state.img_caption)
    st.download_button(
        label="Download PNG",
        data=st.session_state.img_bytes,
        file_name=st.session_state.img_filename,
        mime="image/png",
    )
