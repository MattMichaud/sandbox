import streamlit as st
from datetime import datetime, timedelta
import pandas as pd
import gitlab_data
import tabs


# --- App UI ---
st.set_page_config(page_title="GitLab Digest", page_icon="📝", layout="wide")
st.title("🚀 Merge Request Explorer")


if "projects_data" not in st.session_state:
    cached = gitlab_data.load_projects_cache()
    if cached is not None:
        st.session_state["projects_data"] = cached
    else:
        try:
            with st.spinner("Loading projects and subgroups from GitLab..."):
                st.session_state["projects_data"] = gitlab_data.fetch_projects_from_api()
        except Exception as e:
            st.error(f"Error: {e}")
            st.info("Check your .env file credentials and Group ID.")
            st.stop()

projects_data = st.session_state["projects_data"]
project_map = projects_data["project_map"]
subgroups = projects_data["subgroups"]
root_path = projects_data["root_path"]
project_names = sorted(project_map.keys())

with st.sidebar:
    cached_at = projects_data.get("cached_at")
    if cached_at:
        age = datetime.now() - datetime.fromisoformat(cached_at)
        total_seconds = int(age.total_seconds())
        days, remainder = divmod(total_seconds, 86400)
        hours, remainder = divmod(remainder, 3600)
        minutes = remainder // 60
        if days > 0:
            age_str = f"{days}d {hours}h {minutes}m ago"
        elif hours > 0:
            age_str = f"{hours}h {minutes}m ago"
        else:
            age_str = f"{minutes}m ago"
        st.caption(f"Projects loaded {age_str}")
    if st.button("Reload projects from GitLab"):
        try:
            with st.spinner("Reloading projects and subgroups from GitLab..."):
                st.session_state["projects_data"] = gitlab_data.fetch_projects_from_api()
            st.rerun()
        except Exception as e:
            st.error(f"Error reloading projects: {e}")

    st.header("1. Data Scope")

    if subgroups:
        prefix = root_path + "/"
        sg_dict = {sg["full_path"][len(prefix):]: sg["full_path"] for sg in subgroups}
        # "(all repos)" sorts to top and maps to root, matching every repo
        sg_options = [("(all repos)", root_path)] + sorted(sg_dict.items())
        display_to_full = dict(sg_options)

        selected_display = st.multiselect(
            "Select Team(s)",
            options=[d for d, _ in sg_options],
            default=[],
            help="Selecting a team includes all repositories within it",
        )

        selected_full_paths = {display_to_full[d] for d in selected_display}

        candidate_projects = {
            path: pid
            for path, pid in project_map.items()
            if any(path.startswith(fp + "/") for fp in selected_full_paths)
        }

        if candidate_projects:
            repo_options_all = sorted(candidate_projects.keys())
            repo_filter = st.text_input(
                "Filter Repositories", "",
                help="e.g. 'analytics' or 'api'",
            )
            filtered_repos = [r for r in repo_options_all if repo_filter.lower() in r.lower()]
            select_all_repos = st.checkbox(
                f"Select all {len(filtered_repos)} matching repos", value=True
            )
            selected_project_names = st.multiselect(
                f"Repositories ({len(repo_options_all)} total)",
                options=filtered_repos,
                default=filtered_repos if select_all_repos else [],
            )
        else:
            st.caption("Select a team above to see repositories.")
            selected_project_names = []

    else:
        # Fallback: no COMPANY_GROUP_ID configured — original flat list
        repo_filter = st.text_input(
            "Filter Repos by Name/Path",
            "",
            help="e.g. 'data-platform' or 'marketing'",
        )
        filtered_options = [n for n in project_names if repo_filter.lower() in n.lower()]
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
        if timeframe == "Custom Range" and (not custom_start or not custom_end):
            st.warning("Please select both start and end dates for Custom Range.")
        else:
            s, e = gitlab_data.get_date_range(timeframe, custom_start, custom_end)
            st.session_state["fetch_active"] = True
            st.session_state["locked_projects"] = selected_project_names
            st.session_state["locked_timeframe"] = timeframe
            st.session_state["locked_start"] = s
            st.session_state["locked_end"] = e
            # Clear previous LLM generations when fetching new data
            for key in ("digest_result", "snitch_result", "recap_result", "podcast_script", "podcast_audio",
                        "song_studio_mr", "song_lyria_prompt", "song_audio_bytes"):
                st.session_state.pop(key, None)

# --- Main Action Area ---
if st.session_state.get("fetch_active"):
    active_projects = st.session_state.get("locked_projects")
    active_timeframe = st.session_state.get("locked_timeframe")
    active_start = st.session_state.get("locked_start")
    active_end = st.session_state.get("locked_end")

    if not active_projects:
        st.warning("Please select at least one repository.")
    else:
        cached = st.session_state.get("mr_cache")
        if cached is not None:
            digest_data = cached["data"]
        else:
            progress_bar = st.progress(0, text="Fetching merge requests...")

            def _on_progress(fraction, text):
                progress_bar.progress(fraction, text=text)

            digest_data = gitlab_data.fetch_merge_requests(
                active_projects, active_start, active_end,
                progress_callback=_on_progress,
                project_map=project_map,
            )
            progress_bar.empty()
            st.session_state["mr_cache"] = {"data": digest_data}

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

            tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(
                ["Team Stats", "Executive Digest", "Contributor Recap", "Auto Snitch Tool", "Podcast", "Song Studio"]
            )
            with tab1:
                tabs.render_team_stats_tab(df)
            with tab2:
                tabs.render_digest_tab(digest_data, active_timeframe)
            with tab3:
                tabs.render_recap_tab(digest_data)
            with tab4:
                tabs.render_snitch_tab(digest_data)
            with tab5:
                tabs.render_podcast_tab(digest_data)
            with tab6:
                tabs.render_song_studio_tab(digest_data)
