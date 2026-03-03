import logging
import os

import streamlit as st
from dotenv import load_dotenv

logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(name)s %(levelname)s: %(message)s", datefmt="%Y-%m-%d %H:%M:%S")

import tabs

# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------
st.set_page_config(layout="wide")
load_dotenv()


def _validate_env() -> None:
    required = {"GEMINI_API_KEY": "Copy `.env.example` to `.env` and add your Gemini API key."}
    missing = {var: hint for var, hint in required.items() if not os.getenv(var)}
    if missing:
        for var, hint in missing.items():
            st.error(f"`{var}` not found. {hint}")
        st.stop()


_validate_env()

# ---------------------------------------------------------------------------
# Main UI
# ---------------------------------------------------------------------------
st.title("Claude Plan Image Generator")

tab1, tab2 = st.tabs(["Generate", "Gallery"])
with tab1:
    tabs.render_generate_tab()
with tab2:
    tabs.render_gallery_tab()
