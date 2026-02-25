import streamlit as st
from datetime import datetime, timedelta
import pandas as pd
import gitlab_data
import tabs


# --- App UI ---
st.set_page_config(page_title="GitLab Digest", page_icon="📝", layout="wide")
st.title("🚀 Merge Request Explorer")


try:
    gl = gitlab_data.get_gitlab_client()
    project_map = gitlab_data.fetch_all_projects()
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
            ["Last Full Day", "Last Full Work Week", "Last 30 Days", "Custom Range"],
        )

        custom_start = None
        custom_end = None
        if timeframe == "Custom Range":
            today = datetime.now().date()
            date_range = st.date_input(
                "Select Dates",
                value=(today - timedelta(days=7), today),
                max_value=today,
                format="MM/DD/YYYY",
            )
            if len(date_range) == 2:
                custom_start, custom_end = date_range

        if st.button("Fetch Merge Requests", type="primary"):
            st.session_state["fetch_active"] = True
            st.session_state["locked_projects"] = selected_project_names
            st.session_state["locked_timeframe"] = timeframe

            # Resolve Dates
            if timeframe == "Custom Range" and custom_start and custom_end:
                s = datetime.combine(custom_start, datetime.min.time()).isoformat()
                e = datetime.combine(
                    custom_end + timedelta(days=1), datetime.min.time()
                ).isoformat()
                st.session_state["locked_start"] = s
                st.session_state["locked_end"] = e
            else:
                s, e = gitlab_data.get_date_range(timeframe)
                st.session_state["locked_start"] = s
                st.session_state["locked_end"] = e

            # Clear previous LLM generations when fetching new data
            st.session_state.pop("digest_result", None)
            st.session_state.pop("snitch_result", None)

    # --- Main Action Area ---
    if st.session_state.get("fetch_active"):
        active_projects = st.session_state.get("locked_projects")
        active_timeframe = st.session_state.get("locked_timeframe")
        active_start = st.session_state.get("locked_start")
        active_end = st.session_state.get("locked_end")

        if not active_projects:
            st.warning("Please select at least one repository.")
        else:
            digest_data = gitlab_data.fetch_merge_requests(
                active_projects, active_start, active_end
            )

            if not digest_data:
                st.info("No activity found for these repos in the selected timeframe.")
            else:
                st.subheader("📊 Activity Overview")
                df = pd.DataFrame(digest_data)
                m1, m2, m3 = st.columns(3)
                m1.metric("Total MRs", len(df))
                m2.metric("Total Authors", df["author"].nunique())
                m3.metric("Total Repos", df["repo"].nunique())

                start_dt = datetime.fromisoformat(active_start)
                end_dt = (
                    datetime.fromisoformat(active_end) if active_end else datetime.now()
                )
                date_range_str = (
                    f"{start_dt.strftime('%B %d')} - {end_dt.strftime('%B %d')}"
                )
                st.markdown(f"_:gray[Timeframe: {date_range_str}]_")

                tab1, tab2, tab3 = st.tabs(
                    ["Team Stats", "Executive Digest", "Auto Snitch Tool"]
                )
                with tab1:
                    tabs.render_team_stats_tab(digest_data)
                with tab2:
                    tabs.render_digest_tab(digest_data, active_timeframe)
                with tab3:
                    tabs.render_snitch_tab(digest_data)

except Exception as e:
    st.error(f"Error: {e}")
    st.info("Check your .env file credentials and Group ID.")
