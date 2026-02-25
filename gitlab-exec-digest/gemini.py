import os
import json
import time
from datetime import datetime
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv(override=True)

_client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

_DIGEST_SCHEMA = types.Schema(
    type=types.Type.OBJECT,
    properties={
        "executive_summary": types.Schema(type=types.Type.STRING),
        "impactful_changes": types.Schema(
            type=types.Type.ARRAY,
            items=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "title": types.Schema(type=types.Type.STRING),
                    "description": types.Schema(type=types.Type.STRING),
                    "url": types.Schema(type=types.Type.STRING),
                    "author": types.Schema(type=types.Type.STRING),
                    "context_area": types.Schema(type=types.Type.STRING),
                },
            ),
        ),
        "technical_highlights": types.Schema(
            type=types.Type.ARRAY,
            items=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "title": types.Schema(type=types.Type.STRING),
                    "description": types.Schema(type=types.Type.STRING),
                    "url": types.Schema(type=types.Type.STRING),
                    "author": types.Schema(type=types.Type.STRING),
                },
            ),
        ),
    },
)

_SNITCH_SCHEMA = types.Schema(
    type=types.Type.ARRAY,
    items=types.Schema(
        type=types.Type.OBJECT,
        properties={
            "author": types.Schema(type=types.Type.STRING),
            "demo_title": types.Schema(type=types.Type.STRING),
            "description": types.Schema(type=types.Type.STRING),
            "song_recommendation": types.Schema(type=types.Type.STRING),
            "link": types.Schema(type=types.Type.STRING),
        },
    ),
)

_MODEL = "gemini-3-flash-preview"


def _generate(prompt, config, retries=3, base_delay=2):
    """Call Gemini with exponential backoff on 503 / transient errors."""
    for attempt in range(retries):
        try:
            return _client.models.generate_content(
                model=_MODEL,
                contents=prompt,
                config=config,
            )
        except Exception as e:
            is_last = attempt == retries - 1
            if is_last or "503" not in str(e):
                raise
            delay = base_delay * (2**attempt)
            print(f"Gemini 503 on attempt {attempt + 1}, retrying in {delay}s…")
            time.sleep(delay)


def _build_mr_context(mrs_data):
    """Format MR list into a prompt-ready context string."""
    parts = []
    for mr in mrs_data:
        diff_snippet = "\n".join(mr["diffs"])[:1500]
        parts.append(f"""
---
REPO: {mr['repo']}
TITLE: {mr['title']}
AUTHOR: {mr['author']}
URL: {mr['url']}
DESCRIPTION: {mr['description']}
CODE SNIPPET:
{diff_snippet}
""")
    return "".join(parts)


def summarize_with_gemini(mrs_data, timeframe):
    if not mrs_data:
        return {}

    current_date = datetime.now().strftime("%B %d, %Y")
    total_mrs = len(mrs_data)
    mr_context = _build_mr_context(mrs_data)

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

    DATA:
    {mr_context}
    """

    response = None
    try:
        response = _generate(
            prompt,
            types.GenerateContentConfig(
                temperature=0.2,
                top_p=0.95,
                top_k=40,
                max_output_tokens=8192,
                response_mime_type="application/json",
                response_schema=_DIGEST_SCHEMA,
            ),
        )
        return json.loads(response.text)
    except Exception as e:
        print(f"Summarization failed with Gemini 3: {str(e)}")
        print(f"Raw response text: {response.text if response else 'no response'}")
        return None


def auto_snitch_with_gemini(mrs_data):
    if not mrs_data:
        return []

    mr_context = _build_mr_context(mrs_data)

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
    - "author": The author's name
    - "demo_title": A catchy title for the demo
    - "description": A short blurb explaining what is cool/interesting.
    - "song_recommendation": A song (Artist - Title) that loosely ties to the content of the demo.
    - "link": The URL to the MR.

    DATA:
    {mr_context}
    """

    response = None
    try:
        response = _generate(
            prompt,
            types.GenerateContentConfig(
                temperature=0.4,
                top_p=0.95,
                top_k=40,
                max_output_tokens=8192,
                response_mime_type="application/json",
                response_schema=_SNITCH_SCHEMA,
            ),
        )
        return json.loads(response.text)
    except Exception as e:
        print(f"Auto Snitch failed: {str(e)}")
        print(f"Raw response text: {response.text if response else 'no response'}")
        return None
