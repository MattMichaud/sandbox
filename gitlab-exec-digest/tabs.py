import base64
import streamlit as st
import streamlit.components.v1 as st_components
from datetime import datetime
import pandas as pd
import altair as alt
import gemini
import podcast


def _mr_label(url):
    """Extract a display label (!123) from a GitLab MR URL."""
    mr_num = url.rstrip("/").split("/")[-1]
    return f"!{mr_num}" if mr_num.isdigit() else "MR"


@st.fragment
def render_digest_tab(digest_data, timeframe):
    if st.button("Generate Digest", type="primary"):
        with st.spinner("Analyzing data..."):
            st.session_state["digest_result"] = gemini.summarize_with_gemini(
                digest_data, timeframe
            )

    if "digest_result" not in st.session_state:
        return

    digest_json = st.session_state["digest_result"]

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
            url = item.get("url", "#")
            st.markdown(
                f"- {item.get('description', '')} — *{item.get('author', 'Unknown')}* · [**{_mr_label(url)}**]({url})"
            )
    else:
        st.markdown("_No specific technical highlights._")

    # Reconstruct Markdown for Download
    md_report = f"# Executive Digest - {datetime.now().strftime('%Y-%m-%d')}\n\n"
    md_report += f"## Executive Summary\n{digest_json.get('executive_summary', '')}\n\n"
    md_report += "## Impactful Changes\n"
    for change in changes:
        md_report += f"- **[{change.get('title', 'Untitled')}]({change.get('url', '#')})** - {change.get('context_area', 'General')} (by {change.get('author', 'Unknown')}): {change.get('description', '')}\n"
    md_report += "\n## Technical Highlights\n"
    for item in highlights:
        url = item.get("url", "#")
        md_report += f"- {item.get('description', '')} — *{item.get('author', 'Unknown')}* · [{_mr_label(url)}]({url})\n"

    st.markdown("---")
    st.download_button(
        "Download Digest (.md)",
        md_report,
        file_name=f"digest_{datetime.now().strftime('%Y%m%d')}.md",
    )


@st.fragment
def render_snitch_tab(digest_data):
    if st.button("Auto Snitch", type="primary"):
        with st.spinner("Snitching on teammates..."):
            st.session_state["snitch_result"] = gemini.auto_snitch_with_gemini(
                digest_data
            )

    if "snitch_result" not in st.session_state:
        return

    snitch_data = st.session_state["snitch_result"]

    if snitch_data is None:
        st.error("Failed to parse Gemini response. Check the terminal logs for details.")
        return

    if not snitch_data:
        st.info("No demo-worthy changes found for this timeframe.")
        return

    st.markdown("### 🕵️ Auto Snitch Recommendations")
    for item in snitch_data:
        with st.container(border=True):
            st.markdown(
                f"### [{item.get('demo_title', 'Untitled')}]({item.get('link', '#')})"
            )

            col1, col2 = st.columns([3, 1])
            with col1:
                st.markdown(f"**👤 Author:** {item.get('author', 'Unknown')}")
                st.markdown(item.get("description", ""))
            with col2:
                st.success(
                    f"**🎵 Song Rec**\n\n{item.get('song_recommendation', 'N/A')}",
                    icon="🎧",
                )

    md_report = f"# Auto Snitch - {datetime.now().strftime('%Y-%m-%d')}\n\n"
    for item in snitch_data:
        md_report += f"## [{item.get('demo_title', 'Untitled')}]({item.get('link', '#')})\n"
        md_report += f"**Author:** {item.get('author', 'Unknown')}\n\n"
        md_report += f"{item.get('description', '')}\n\n"
        md_report += f"🎵 *{item.get('song_recommendation', '')}*\n\n"

    st.markdown("---")
    st.download_button(
        "Download Snitch Report (.md)",
        md_report,
        file_name=f"snitch_{datetime.now().strftime('%Y%m%d')}.md",
    )


@st.fragment
def render_team_stats_tab(df):
    st.markdown("### 📈 Team Behavior Dashboard")

    if df.empty:
        st.info("No data available.")
        return

    df = df.copy()

    # Pre-processing
    df["created_at"] = pd.to_datetime(df["created_at"])
    df["merged_at"] = pd.to_datetime(df["merged_at"])
    df["cycle_time_hours"] = (
        df["merged_at"] - df["created_at"]
    ).dt.total_seconds() / 3600

    # Ramsey Solutions Blue
    ramsey_blue = "#004B8D"

    # --- Top Level Stats ---
    col_a, col_b = st.columns(2)

    with col_a:
        st.markdown("#### 👨‍💻 Top Authors")
        author_counts = (
            df["author"]
            .value_counts()
            .head(10)
            .rename_axis("author")
            .reset_index(name="count")
        )
        chart_author = (
            alt.Chart(author_counts)
            .mark_bar(color=ramsey_blue)
            .encode(
                x=alt.X("count", title="MR Count"),
                y=alt.Y("author", sort="-x", title=None),
                tooltip=["author", "count"],
            )
            .configure_axis(grid=False)
            .configure_view(strokeWidth=0)
        )
        st.altair_chart(chart_author, width="stretch")

    with col_b:
        st.markdown("#### 📂 Top Repositories")
        repo_counts = (
            df["repo"]
            .value_counts()
            .head(10)
            .rename_axis("repo")
            .reset_index(name="count")
        )
        # Map repo name to repo_url
        repo_url_map = df[["repo", "repo_url"]].drop_duplicates().set_index("repo")
        repo_counts = repo_counts.join(repo_url_map, on="repo")

        repo_counts["repo_short"] = repo_counts["repo"].apply(
            lambda x: x.split("/")[-1]
        )
        chart_repo = (
            alt.Chart(repo_counts)
            .mark_bar(color=ramsey_blue)
            .encode(
                x=alt.X("count", title="MR Count"),
                y=alt.Y("repo_short", sort="-x", title=None),
                tooltip=["repo", "count"],
                href="repo_url",
            )
            .properties(usermeta={"embedOptions": {"loader": {"target": "_blank"}}})
            .configure_axis(grid=False)
            .configure_view(strokeWidth=0)
        )
        st.altair_chart(chart_repo, width="stretch")

    # Layout
    col1, col2 = st.columns(2)

    # 1. Top Reviewers
    with col1:
        st.markdown("#### 🏆 Top Reviewers")
        reviewers_exploded = df.explode("reviewers")
        if (
            "reviewers" in reviewers_exploded.columns
            and not reviewers_exploded["reviewers"].isna().all()
        ):
            reviewer_counts = (
                reviewers_exploded["reviewers"].value_counts().reset_index()
            )
            reviewer_counts.columns = ["reviewer", "count"]

            chart_reviewers = (
                alt.Chart(reviewer_counts.head(10))
                .mark_bar(color=ramsey_blue)
                .encode(
                    x=alt.X("count", title="MRs Reviewed"),
                    y=alt.Y("reviewer", sort="-x", title=None),
                    tooltip=["reviewer", "count"],
                )
                .configure_axis(grid=False)
                .configure_view(strokeWidth=0)
            )
            st.altair_chart(chart_reviewers, width="stretch")
        else:
            st.caption("No reviewer data found.")

    # 2. Most Discussed MRs
    with col2:
        st.markdown("#### 💬 Most Discussed MRs")
        top_discussed = df.nlargest(10, "comments")
        chart_comments = (
            alt.Chart(top_discussed)
            .mark_bar(color=ramsey_blue)
            .encode(
                x=alt.X("comments", title="Comment Count"),
                y=alt.Y(
                    "title", sort="-x", title=None, axis=alt.Axis(labels=False)
                ),  # Hide labels if titles are long
                tooltip=["title", "author", "comments"],
                href="url",
            )
            .properties(usermeta={"embedOptions": {"loader": {"target": "_blank"}}})
            .configure_axis(grid=False)
            .configure_view(strokeWidth=0)
        )
        st.altair_chart(chart_comments, width="stretch")

    col3, col4 = st.columns(2)

    # 3. Cycle Time Distribution
    with col3:
        st.markdown("#### ⏱️ Cycle Time (Hours)")
        chart_cycle = (
            alt.Chart(df)
            .mark_bar(color=ramsey_blue)
            .encode(
                x=alt.X("cycle_time_hours", bin=True, title="Hours to Merge"),
                y=alt.Y("count()", title="MR Count"),
                tooltip=["count()"],
            )
            .configure_axis(grid=False)
            .configure_view(strokeWidth=0)
        )
        st.altair_chart(chart_cycle, width="stretch")

    # 4. Throughput by Day
    with col4:
        st.markdown("#### 📅 Merges by Day of Week")
        df["day_of_week"] = df["merged_at"].dt.day_name()
        days_order = [
            "Monday",
            "Tuesday",
            "Wednesday",
            "Thursday",
            "Friday",
            "Saturday",
            "Sunday",
        ]

        chart_days = (
            alt.Chart(df)
            .mark_bar(color=ramsey_blue)
            .encode(
                x=alt.X("day_of_week", sort=days_order, title=None),
                y=alt.Y("count()", title="MR Count"),
                tooltip=["day_of_week", "count()"],
            )
            .configure_axis(grid=False)
            .configure_view(strokeWidth=0)
        )
        st.altair_chart(chart_days, width="stretch")


@st.fragment
def render_podcast_tab(digest_data):
    st.markdown("### 🎙️ Podcast Generator")
    st.caption("Generate a two-host conversational podcast from your MR data.")

    col1, col2 = st.columns([1, 2])

    with col1:
        _PRESET_ROLES = [
            "Engineering Leader",
            "Data & Analytics Leader",
            "Business Leader",
            "Custom",
        ]
        selected_role = st.radio("Listener Role", options=_PRESET_ROLES, index=1)
        if selected_role == "Custom":
            custom_role = st.text_input(
                "Describe the listener's role",
                placeholder="e.g. Product Manager, CFO, Sales Leader",
            )
            role = custom_role.strip() or "a general professional audience"
        else:
            role = selected_role

        length_minutes = st.radio(
            "Podcast Length",
            options=[1, 5, 10],
            format_func=lambda x: f"{x} min",
            index=1,
        )
        rate_percent = st.slider("Speech Rate", min_value=0, max_value=25, value=10, format="+%d%%")
        if st.button("Generate Podcast", type="primary"):
            with st.spinner("Writing script..."):
                script = gemini.generate_podcast_script(
                    digest_data, length_minutes, role, rate_percent
                )
            if not script:
                st.error("Failed to generate podcast script. Please try again.")
            else:
                st.session_state["podcast_script"] = script
                st.session_state.pop("podcast_audio", None)
                with st.spinner("Synthesizing audio (this may take a moment)..."):
                    audio_bytes = podcast.generate_podcast_audio(script, rate_percent)
                st.session_state["podcast_audio"] = audio_bytes

    with col2:
        if "podcast_script" not in st.session_state:
            return

        script = st.session_state["podcast_script"]
        audio_bytes = st.session_state.get("podcast_audio")

        st.subheader(script.get("title", "Untitled Episode"))

        if audio_bytes:
            audio_b64 = base64.b64encode(audio_bytes).decode()
            st_components.html(
                f"""
                <style>
                  .pod-player {{ display:flex; align-items:center; gap:10px; flex-wrap:wrap;
                                 font-family:sans-serif; padding:4px 0; }}
                  audio {{ flex:1; min-width:200px; }}
                  .speed-btn {{ padding:4px 10px; border:1px solid #ccc; border-radius:6px;
                                background:#f0f0f0; cursor:pointer; font-size:13px; }}
                  .speed-btn.active {{ background:#004B8D; color:#fff; border-color:#004B8D; }}
                </style>
                <div class="pod-player">
                  <audio id="pod" controls>
                    <source src="data:audio/mpeg;base64,{audio_b64}" type="audio/mpeg">
                  </audio>
                  <button class="speed-btn active" onclick="setSpeed(1.0, this)">1×</button>
                  <button class="speed-btn" onclick="setSpeed(1.25, this)">1.25×</button>
                  <button class="speed-btn" onclick="setSpeed(1.5, this)">1.5×</button>
                </div>
                <script>
                  function setSpeed(rate, btn) {{
                    document.getElementById('pod').playbackRate = rate;
                    document.querySelectorAll('.speed-btn').forEach(b => b.classList.remove('active'));
                    btn.classList.add('active');
                  }}
                </script>
                """,
                height=64,
            )
            st.download_button(
                "Download MP3",
                data=audio_bytes,
                file_name=f"podcast_{datetime.now().strftime('%Y%m%d')}.mp3",
                mime="audio/mpeg",
            )
        else:
            st.warning("Audio generation failed or is unavailable.")

        with st.expander("Show Transcript"):
            for seg in script.get("segments", []):
                speaker = seg.get("speaker", "Host")
                text = seg.get("text", "")
                st.markdown(f"**{speaker}:** {text}")
