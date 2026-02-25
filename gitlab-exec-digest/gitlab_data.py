import streamlit as st
import gitlab
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv
import concurrent.futures

load_dotenv(override=True)


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
        projects = group.projects.list(
            get_all=True, simple=True, include_subgroups=True, all_levels=True
        )
    else:
        projects = gl.projects.list(get_all=True, simple=True, membership=True)

    return {p.path_with_namespace: p.id for p in projects}


def get_date_range(timeframe_label, custom_start=None, custom_end=None):
    now = datetime.now()

    if timeframe_label == "Last Full Day":
        end_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
        start_date = end_date - timedelta(days=1)
        return start_date.isoformat(), end_date.isoformat()

    elif timeframe_label == "Last Full Work Week":
        today = now.date()
        # Find the most recently completed Saturday.
        # weekday(): Mon=0, Tue=1, Wed=2, Thu=3, Fri=4, Sat=5, Sun=6
        # If today is Saturday, use the previous one (not the current in-progress day).
        days_since_sat = (today.weekday() - 5) % 7 or 7
        last_saturday = today - timedelta(days=days_since_sat)
        end_dt = datetime.combine(last_saturday + timedelta(days=1), datetime.min.time())
        start_dt = end_dt - timedelta(days=7)
        return start_dt.isoformat(), end_dt.isoformat()

    elif timeframe_label == "Last 30 Days":
        end_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
        start_date = end_date - timedelta(days=30)
        return start_date.isoformat(), end_date.isoformat()

    elif timeframe_label == "Custom Range":
        if custom_start is None or custom_end is None:
            raise ValueError("Custom Range requires both custom_start and custom_end")
        s = datetime.combine(custom_start, datetime.min.time()).isoformat()
        e = datetime.combine(custom_end + timedelta(days=1), datetime.min.time()).isoformat()
        return s, e

    raise ValueError(f"Unknown timeframe: {timeframe_label!r}")


def _fetch_single_project_mrs(gl, pid, name, updated_after, updated_before):
    """Fetch MRs for a single project (runs in thread)."""
    project_data = []
    try:
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
                    "author": mr.author.get("name", "Unknown"),
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


def fetch_merge_requests(project_names, updated_after, updated_before, progress_callback=None):
    gl = get_gitlab_client()
    project_map = fetch_all_projects()
    digest_data = []

    valid_projects = [
        (name, project_map[name]) for name in project_names if name in project_map
    ]
    total_projects = len(valid_projects)

    if total_projects == 0:
        return []

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        future_to_name = {
            executor.submit(
                _fetch_single_project_mrs, gl, pid, name, updated_after, updated_before
            ): name
            for name, pid in valid_projects
        }

        for i, future in enumerate(concurrent.futures.as_completed(future_to_name)):
            name = future_to_name[future]
            if progress_callback:
                progress_callback(
                    (i + 1) / total_projects,
                    f"Fetching {name} ({i + 1}/{total_projects})...",
                )
            try:
                data = future.result()
                digest_data.extend(data)
            except Exception as e:
                print(f"Exception in thread for {name}: {e}")

    return digest_data
