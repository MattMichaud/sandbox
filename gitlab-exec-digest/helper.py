import streamlit as st
import gitlab
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv
import google.generativeai as genai
import json

load_dotenv(override=True)

# Configure Gemini
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))


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


@st.cache_data(ttl=300, show_spinner=False)
def fetch_merge_requests(project_names, timeframe):
    gl = get_gitlab_client()
    project_map = fetch_all_projects()
    created_after = get_start_date(timeframe)
    digest_data = []

    progress_bar = st.progress(0)
    status_text = st.empty()
    total_projects = len(project_names)

    for i, name in enumerate(project_names):
        progress_bar.progress(i / total_projects)
        status_text.text(f"Fetching {name}...")

        if name not in project_map:
            continue

        pid = project_map[name]
        try:
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
                        "url": mr.web_url,
                        "description": mr.description,
                        "author": mr.author["name"],
                        "merged_at": mr.merged_at,
                        "changes_count": len(changes["changes"]),
                        "diffs": [c["diff"] for c in changes["changes"]],
                    }
                )
        except Exception as e:
            print(f"Error fetching {name}: {e}")
            continue

    progress_bar.empty()
    status_text.empty()

    return digest_data


def summarize_with_gemini(mrs_data, timeframe):
    if not mrs_data:
        return {}

    current_date = datetime.now().strftime("%B %d, %Y")
    total_mrs = len(mrs_data)
    # Use the specific model string from your capability list
    # Gemini 3 Flash is ideal for this kind of text-heavy summarization
    generation_config = {
        "temperature": 0.2,
        "top_p": 0.95,
        "top_k": 40,
        "max_output_tokens": 4096,
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
URL: {mr['url']}
DESCRIPTION: {mr['description']}
CODE SNIPPET:
{diff_snippet}
"""

    prompt = f"""
    You are a Technical Chief of Staff. Review these Merge Requests from the {timeframe} 
    and create an "Impact Digest" for a company executive.
    
    Today's Date: {current_date}
    
    The executive wants to see high-level progress and interesting technical wins.
    
    Output a strict JSON object with the following keys:
    - "executive_summary": 1-2 sentences on overall velocity. Mention that {total_mrs} MRs were merged.
    - "impactful_changes": A list of objects (max 5), each containing:
        - "title": A concise, business-friendly title summarizing the impact (do not use the raw MR title).
        - "description": A focus on the "Why" (business/technical value).
        - "url": The MR URL.
        - "author": The MR Author's name.
        - "context_area": Inferred business area, application name, or technology (e.g. "Payments", "Frontend", "Infrastructure").
    - "technical_highlights": A list of strings noting interesting architectural choices or refactors.
    
    Do not use Markdown formatting (no ```json blocks). Just output the raw JSON.

    DATA:
    {mr_context}
    """

    try:
        response = model.generate_content(prompt)
        text = response.text.strip()
        # Clean up markdown if the model ignores the instruction
        if text.startswith("```json"):
            text = text[7:]
        if text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        return json.loads(text)
    except Exception as e:
        print(f"Summarization failed with Gemini 3: {str(e)}")
        return {}


def auto_snitch_with_gemini(mrs_data):
    if not mrs_data:
        return []

    generation_config = {
        "temperature": 0.4,
        "top_p": 0.95,
        "top_k": 40,
        "max_output_tokens": 4096,
    }

    model = genai.GenerativeModel(
        model_name="gemini-3-flash-preview", generation_config=generation_config
    )

    # Build the context string
    mr_context = ""
    for mr in mrs_data:
        diff_snippet = "\n".join(mr["diffs"])[:1500]

        mr_context += f"""
---
REPO: {mr['repo']}
TITLE: {mr['title']}
AUTHOR: {mr['author']}
URL: {mr['url']}
DESCRIPTION: {mr['description']}
CODE SNIPPET:
{diff_snippet}
"""

    prompt = f"""
    You are a Team Lead preparing for the weekly engineering demo meeting. 
    Review these Merge Requests and identify interesting, unique, or "cool" changes that should be shared with the team.
    
    Look for:
    - New user-facing features
    - Clever code techniques or refactors
    - Performance improvements
    - Anything that would make for a good 5-minute demo

    Constraint: Try to maximize the diversity of authors. Do not select the same author more than once unless they are the only ones with activity.

    Output a strict JSON list of objects. 
    Each object must have the following keys:
    - "Author": The author's name
    - "Demo Title": A catchy title for the demo
    - "Description": A short blurb explaining what is cool/interesting.
    - "Song Recommendation": A song (Artist - Title) that loosely ties to the content of the demo.
    - "Link": The URL to the MR.

    Do not use Markdown formatting (no ```json blocks). Just output the raw JSON.

    DATA:
    {mr_context}
    """

    try:
        response = model.generate_content(prompt)
        text = response.text.strip()
        # Clean up markdown if the model ignores the instruction
        if text.startswith("```json"):
            text = text[7:]
        if text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]

        return json.loads(text)
    except Exception as e:
        print(f"Auto Snitch failed: {str(e)}")
        return []
