import os

import streamlit as st
from dotenv import load_dotenv

from gemini import generate_image, markdown_to_image_prompt
from plans import PLANS_DIR, format_plan_option, list_plans

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
