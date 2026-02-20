import streamlit as st
import gitlab
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv
import google.generativeai as genai

load_dotenv()


# --- GitLab Connection ---
@st.cache_resource
def get_gitlab_client():
    return gitlab.Gitlab(
        url=os.getenv("GITLAB_URL"), private_token=os.getenv("GITLAB_TOKEN")
    )


@st.cache_data(ttl=3600)
def fetch_all_projects():
    gl = get_gitlab_client()
    group_id = os.getenv("COMPANY_GROUP_ID")

    if group_id:
        group = gl.groups.get(group_id)
        # include_subgroups=True ensures we see projects in nested squads/divisions
        projects = group.projects.list(
            get_all=True, simple=True, include_subgroups=True, all_levels=True
        )
    else:
        projects = gl.projects.list(get_all=True, simple=True, membership=True)

    return {p.path_with_namespace: p.id for p in projects}


# -- Helper Function ---
def get_start_date(timeframe_label):
    now = datetime.now()
    if timeframe_label == "Last Day":
        delta = timedelta(days=1)
    elif timeframe_label == "Last Week":
        delta = timedelta(weeks=1)
    else:  # Last Month
        delta = timedelta(days=30)
    return (now - delta).isoformat()


# Configure Gemini
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))


def summarize_with_gemini(mrs_data, timeframe):
    if not mrs_data:
        return "No significant activity found for this period."

    # Use the specific model string from your capability list
    # Gemini 3 Flash is ideal for this kind of text-heavy summarization
    generation_config = {
        "temperature": 0.2,
        "top_p": 0.95,
        "top_k": 40,
        "max_output_tokens": 2048,
    }

    model = genai.GenerativeModel(
        model_name="gemini-3-flash-preview", generation_config=generation_config
    )

    # Build the context string
    mr_context = ""
    for mr in mrs_data:
        diff_snippet = "\n".join(mr["diffs"])[
            :1500
        ]  # Increased limit slightly for Gemini 3

        mr_context += f"""
---
REPO: {mr['repo']}
TITLE: {mr['title']}
AUTHOR: {mr['author']}
DESCRIPTION: {mr['description']}
CODE SNIPPET:
{diff_snippet}
"""

    prompt = f"""
    You are a Technical Chief of Staff. Review these Merge Requests from the {timeframe} 
    and create an "Impact Digest" for a company executive.
    
    The executive wants to see high-level progress and interesting technical wins.
    
    STRUCTURE:
    1. **Executive Summary**: 1-2 sentences on overall velocity.
    2. **Impactful Changes**: Highlight 3-5 major changes. Focus on the "Why" (e.g., improves scaling, reduces cost, enhances user experience).
    3. **Technical Highlights**: Note any interesting architectural choices or refactors found in the diffs.
    
    Avoid jargon. Focus on business and technical value.

    DATA:
    {mr_context}
    """

    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"Summarization failed with Gemini 3: {str(e)}"


# --- App UI ---
st.set_page_config(page_title="GitLab Digest", page_icon="📝", layout="wide")
st.title("🚀 Merge Request Digest")

try:
    gl = get_gitlab_client()
    project_map = fetch_all_projects()
    project_names = sorted(project_map.keys())

    with st.sidebar:
        st.header("1. Data Scope")

        # Pattern Filtering Logic
        repo_filter = st.text_input(
            "Filter Repos by Name/Path", "", help="e.g. 'data-platform' or 'marketing'"
        )

        filtered_options = [
            name for name in project_names if repo_filter.lower() in name.lower()
        ]

        # Select All Logic
        select_all = st.checkbox(
            f"Select all {len(filtered_options)} filtered repos", value=False
        )

        selected_project_names = st.multiselect(
            "Select Specific Repositories",
            options=filtered_options,
            default=filtered_options if select_all else [],
        )

        st.header("2. Timeframe")
        timeframe = st.selectbox(
            "Select Range", ["Last Day", "Last Week", "Last Month"]
        )

    # --- Main Action Area ---
    if st.button("Generate Digest", type="primary"):
        if not selected_project_names:
            st.warning("Please select at least one repository.")
        else:
            created_after = get_start_date(timeframe)
            digest_data = []

            progress_bar = st.progress(0)
            status_text = st.empty()

            for i, name in enumerate(selected_project_names):
                percent_complete = int((i / len(selected_project_names)) * 100)
                progress_bar.progress(percent_complete)
                status_text.text(f"Scanning {name}...")

                pid = project_map[name]
                project = gl.projects.get(pid)

                # Fetching Merged MRs
                mrs = project.mergerequests.list(
                    state="merged", updated_after=created_after, get_all=True
                )

                for mr in mrs:
                    # Renovate Bot Exclusion
                    author_username = mr.author.get("username", "").lower()
                    author_name = mr.author.get("name", "").lower()
                    if "renovate" in author_username or "renovate" in author_name:
                        continue

                    changes = mr.changes()
                    digest_data.append(
                        {
                            "repo": name,
                            "title": mr.title,
                            "description": mr.description,
                            "author": mr.author["name"],
                            "merged_at": mr.merged_at,
                            "changes_count": len(changes["changes"]),
                            "diffs": [c["diff"] for c in changes["changes"]],
                        }
                    )

            progress_bar.empty()
            status_text.empty()

            if not digest_data:
                st.info("No activity found for these repos in the selected timeframe.")
            else:
                with st.spinner("Analyzing data..."):
                    final_report = summarize_with_gemini(digest_data, timeframe)

                st.markdown("---")
                st.markdown(final_report)
                st.download_button(
                    "Download Digest (.md)",
                    final_report,
                    file_name=f"digest_{datetime.now().strftime('%Y%m%d')}.md",
                )

except Exception as e:
    st.error(f"Error: {e}")
    st.info("Check your .env file credentials and Group ID.")
