import streamlit as st
import gitlab
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv
from google import genai
from google.genai import types
import json
import time
import concurrent.futures

load_dotenv(override=True)

# Configure Gemini
_gemini_client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))


def _gemini_generate(prompt, config, retries=3, base_delay=2):
    """Call Gemini with exponential backoff on 503 / transient errors."""
    for attempt in range(retries):
        try:
            return _gemini_client.models.generate_content(
                model="gemini-3-flash-preview",
                contents=prompt,
                config=config,
            )
        except Exception as e:
            is_last = attempt == retries - 1
            if is_last or "503" not in str(e):
                raise
            delay = base_delay ** attempt
            print(f"Gemini 503 on attempt {attempt + 1}, retrying in {delay}s…")
            time.sleep(delay)


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
def get_date_range(timeframe_label):
    now = datetime.now()

    if timeframe_label == "Last Full Day":
        end_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
        start_date = end_date - timedelta(days=1)
        return start_date.isoformat(), end_date.isoformat()

    elif timeframe_label == "Last Full Work Week":
        # Previous Sunday through Saturday
        today = now.date()
        # Calculate days to subtract to get to last Saturday
        days_to_last_sat = (today.weekday() + 2) % 7
        if days_to_last_sat == 0:
            days_to_last_sat = 7
        last_saturday = today - timedelta(days=days_to_last_sat)
        end_dt = datetime.combine(
            last_saturday + timedelta(days=1), datetime.min.time()
        )
        start_dt = end_dt - timedelta(days=7)
        return start_dt.isoformat(), end_dt.isoformat()

    elif timeframe_label == "Last 30 Days":
        end_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
        start_date = end_date - timedelta(days=30)
        return start_date.isoformat(), end_date.isoformat()

    return None, None


def _fetch_single_project_mrs(gl, pid, name, updated_after, updated_before):
    """Helper function to fetch MRs for a single project (runs in thread)."""
    project_data = []
    try:
        # lazy=True avoids an API call to get project details
        project = gl.projects.get(pid, lazy=True)

        kwargs = {
            "state": "merged",
            "updated_after": updated_after,
            "get_all": True,
        }
        if updated_before:
            kwargs["updated_before"] = updated_before

        mrs = project.mergerequests.list(**kwargs)

        for mr in mrs:
            # Renovate Bot Exclusion
            author_username = mr.author.get("username", "").lower()
            author_name = mr.author.get("name", "").lower()
            if "renovate" in author_username or "renovate" in author_name:
                continue

            changes = mr.changes()
            project_data.append(
                {
                    "repo": name,
                    "repo_url": mr.web_url.split("/-/")[0],
                    "title": mr.title,
                    "url": mr.web_url,
                    "description": mr.description,
                    "author": mr.author["name"],
                    "merged_at": mr.merged_at,
                    "created_at": mr.created_at,
                    "changes_count": len(changes["changes"]),
                    "diffs": [c["diff"] for c in changes["changes"]],
                    "reviewers": (
                        [r["name"] for r in mr.reviewers]
                        if hasattr(mr, "reviewers")
                        else []
                    ),
                    "labels": mr.labels,
                    "comments": mr.user_notes_count,
                }
            )
    except Exception as e:
        print(f"Error fetching {name}: {e}")

    return project_data


@st.cache_data(ttl=300, show_spinner=False)
def fetch_merge_requests(project_names, updated_after, updated_before):
    gl = get_gitlab_client()
    project_map = fetch_all_projects()
    digest_data = []

    # Filter to valid projects first
    valid_projects = [
        (name, project_map[name]) for name in project_names if name in project_map
    ]
    total_projects = len(valid_projects)

    if total_projects == 0:
        return []

    progress_bar = st.progress(0)
    status_text = st.empty()

    # Use ThreadPoolExecutor for parallel fetching
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        future_to_name = {
            executor.submit(
                _fetch_single_project_mrs, gl, pid, name, updated_after, updated_before
            ): name
            for name, pid in valid_projects
        }

        for i, future in enumerate(concurrent.futures.as_completed(future_to_name)):
            name = future_to_name[future]
            progress_bar.progress((i + 1) / total_projects)
            status_text.text(f"Fetching {name} ({i + 1}/{total_projects})...")

            try:
                data = future.result()
                digest_data.extend(data)
            except Exception as e:
                print(f"Exception in thread for {name}: {e}")

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
    - "impactful_changes": A list of objects (max 5) focusing strictly on BUSINESS VALUE and USER IMPACT.
        - "title": A concise, business-friendly title summarizing the impact (do not use the raw MR title).
        - "description": A focus on the "Why" (business value).
        - "url": The MR URL.
        - "author": The MR Author's name.
        - "context_area": Inferred business area, application name, or technology (e.g. "Payments", "Frontend", "Infrastructure").
    - "technical_highlights": A list of objects (up to 10) noting interesting architectural choices, refactors, or library updates.
        - "title": A short, specific title describing the technical change.
        - "description": Focus strictly on the "How" (engineering details). Do NOT repeat high-level features listed in "impactful_changes".
        - "url": The URL of the MR this change belongs to.
        - "author": The name of the author who made the change.
    
    Do not use Markdown formatting (no ```json blocks). Just output the raw JSON.

    DATA:
    {mr_context}
    """

    try:
        response = _gemini_generate(
            prompt,
            types.GenerateContentConfig(
                temperature=0.2,
                top_p=0.95,
                top_k=40,
                max_output_tokens=4096,
            ),
        )
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
        response = _gemini_generate(
            prompt,
            types.GenerateContentConfig(
                temperature=0.4,
                top_p=0.95,
                top_k=40,
                max_output_tokens=4096,
            ),
        )
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
