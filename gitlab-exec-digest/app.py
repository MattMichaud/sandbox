import streamlit as st
from datetime import datetime
import pandas as pd
import altair as alt
import helper
import importlib


# --- App UI ---
st.set_page_config(page_title="GitLab Digest", page_icon="📝", layout="wide")
st.title("🚀 Merge Request Explorer")


@st.fragment
def render_digest_tab(digest_data, timeframe):
    if st.button("Generate Digest", type="primary"):
        with st.spinner("Analyzing data..."):
            digest_json = helper.summarize_with_gemini(digest_data, timeframe)

        if not digest_json:
            st.error("Failed to generate digest. Please try again.")
            return

        # 1. Executive Summary
        st.markdown("### 📋 Executive Summary")
        st.info(digest_json.get("executive_summary", "No summary available."))

        # 2. Impactful Changes
        st.markdown("### 💥 Impactful Changes")
        changes = digest_json.get("impactful_changes", [])
        if changes:
            for change in changes:
                with st.container(border=True):
                    st.markdown(
                        f"#### [{change.get('title', 'Untitled')}]({change.get('url', '#')})"
                    )
                    st.markdown(change.get("description", "No description."))
                    st.caption(
                        f"👤 **{change.get('author', 'Unknown')}** | 🏷️ *{change.get('context_area', 'General')}*"
                    )
        else:
            st.markdown("_No major impactful changes identified._")

        # 3. Technical Highlights
        st.markdown("### 🛠️ Technical Highlights")
        highlights = digest_json.get("technical_highlights", [])
        if highlights:
            for item in highlights:
                st.markdown(f"- {item}")
        else:
            st.markdown("_No specific technical highlights._")

        # Reconstruct Markdown for Download
        md_report = f"# Executive Digest - {datetime.now().strftime('%Y-%m-%d')}\n\n"
        md_report += (
            f"## Executive Summary\n{digest_json.get('executive_summary', '')}\n\n"
        )
        md_report += "## Impactful Changes\n"
        for change in changes:
            md_report += f"- **[{change.get('title', 'Untitled')}]({change.get('url', '#')})** - {change.get('context_area', 'General')} (by {change.get('author', 'Unknown')}): {change.get('description', '')}\n"
        md_report += "\n## Technical Highlights\n"
        for item in highlights:
            md_report += f"- {item}\n"

        st.markdown("---")
        st.download_button(
            "Download Digest (.md)",
            md_report,
            file_name=f"digest_{datetime.now().strftime('%Y%m%d')}.md",
        )


@st.fragment
def render_snitch_tab(digest_data):
    if st.button("Auto Snitch"):
        with st.spinner("Snitching on teammates..."):
            snitch_data = helper.auto_snitch_with_gemini(digest_data)

        st.markdown("### 🕵️ Auto Snitch Recommendations")

        if snitch_data:
            for item in snitch_data:
                with st.container(border=True):
                    st.markdown(
                        f"### [{item.get('Demo Title', 'Untitled')}]({item.get('Link', '#')})"
                    )

                    col1, col2 = st.columns([3, 1])
                    with col1:
                        st.markdown(f"**👤 Author:** {item.get('Author', 'Unknown')}")
                        st.markdown(item.get("Description", ""))
                    with col2:
                        st.success(
                            f"**🎵 Song Rec**\n\n{item.get('Song Recommendation', 'N/A')}",
                            icon="🎧",
                        )
        else:
            st.info("No recommendations found or error parsing results.")


try:
    importlib.reload(helper)
    gl = helper.get_gitlab_client()
    project_map = helper.fetch_all_projects()
    # print(f"DEBUG: Fetched {len(project_map)} projects")
    project_names = sorted(project_map.keys())

    with st.sidebar:
        st.header("1. Data Scope")

        # Pattern Filtering Logic
        repo_filter = st.text_input(
            "Filter Repos by Name/Path",
            "",
            help="e.g. 'data-platform' or 'marketing'",
        )

        filtered_options = [
            name for name in project_names if repo_filter.lower() in name.lower()
        ]

        # Select All Logic
        select_all = st.checkbox(
            f"Select all {len(filtered_options)} filtered repos",
            value=False,
        )

        selected_project_names = st.multiselect(
            "Select Specific Repositories",
            options=filtered_options,
            default=filtered_options if select_all else [],
        )

        st.header("2. Timeframe")
        timeframe = st.selectbox(
            "Select Range",
            ["Last Day", "Last Week", "Last Month"],
        )

        if st.button("Fetch Merge Requests", type="primary"):
            st.session_state["fetch_active"] = True
            st.session_state["locked_projects"] = selected_project_names
            st.session_state["locked_timeframe"] = timeframe

    # --- Main Action Area ---
    if st.session_state.get("fetch_active"):
        active_projects = st.session_state.get("locked_projects")
        active_timeframe = st.session_state.get("locked_timeframe")

        if not active_projects:
            st.warning("Please select at least one repository.")
        else:
            digest_data = helper.fetch_merge_requests(active_projects, active_timeframe)

            if not digest_data:
                st.info("No activity found for these repos in the selected timeframe.")
            else:
                st.subheader("📊 Activity Overview")
                df = pd.DataFrame(digest_data)
                col1, col2 = st.columns(2)

                with col1:
                    author_counts = (
                        df["author"]
                        .value_counts()
                        .head(10)
                        .rename_axis("author")
                        .reset_index(name="count")
                    )
                    chart_author = (
                        alt.Chart(author_counts)
                        .mark_bar()
                        .encode(
                            x=alt.X("count", title="MR Count"),
                            y=alt.Y("author", sort="-x", title=None),
                            tooltip=["author", "count"],
                            color=alt.Color("count", legend=None),
                        )
                        .properties(title="Top 10 Authors")
                    )
                    st.altair_chart(chart_author, use_container_width=True)

                with col2:
                    repo_counts = (
                        df["repo"]
                        .value_counts()
                        .head(10)
                        .rename_axis("repo")
                        .reset_index(name="count")
                    )
                    chart_repo = (
                        alt.Chart(repo_counts)
                        .mark_bar()
                        .encode(
                            x=alt.X("count", title="MR Count"),
                            y=alt.Y("repo", sort="-x", title=None),
                            tooltip=["repo", "count"],
                            color=alt.Color("count", legend=None),
                        )
                        .properties(title="Top 10 Repositories")
                    )
                    st.altair_chart(chart_repo, use_container_width=True)

                tab1, tab2 = st.tabs(["Executive Digest", "Auto Snitch Tool"])
                with tab1:
                    render_digest_tab(digest_data, active_timeframe)
                with tab2:
                    render_snitch_tab(digest_data)

except Exception as e:
    st.error(f"Error: {e}")
    st.info("Check your .env file credentials and Group ID.")
