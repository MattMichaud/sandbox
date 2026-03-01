import os

import streamlit as st
from dotenv import load_dotenv

import tabs

# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------
st.set_page_config(layout="wide")
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

tab1, tab2 = st.tabs(["Generate", "Gallery"])
with tab1:
    tabs.render_generate_tab()
with tab2:
    tabs.render_gallery_tab()
