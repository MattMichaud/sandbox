import os
import json
import time
from datetime import datetime
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv(override=True)

_client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
_MODEL = "gemini-3-flash-preview"

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
            "spark_score": types.Schema(type=types.Type.INTEGER),
        },
    ),
)

_PODCAST_SCHEMA = types.Schema(
    type=types.Type.OBJECT,
    properties={
        "title": types.Schema(type=types.Type.STRING),
        "segments": types.Schema(
            type=types.Type.ARRAY,
            items=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "speaker": types.Schema(type=types.Type.STRING),
                    "text": types.Schema(type=types.Type.STRING),
                },
            ),
        ),
    },
)

_WORD_COUNT_TARGETS = {
    5: 750,
    10: 1500,
}

_ROLE_FRAMING = {
    "Engineering Leader": {
        "audience": "an engineering director or VP of Engineering",
        "emphasis": "team velocity, technical decision-making, architecture choices, code quality trends, and engineering productivity",
        "language": "technical but strategic — assume the listener is comfortable with software engineering concepts",
        "title_style": 'e.g. "Engineering Pulse: [topic]"',
    },
    "Data & Analytics Leader": {
        "audience": "a Head of Data, Analytics Engineering Manager, or Chief Data Officer",
        "emphasis": "data pipeline changes, analytics infrastructure, data quality, modeling improvements, and tooling updates",
        "language": "data-fluent — use analytics and data engineering terminology naturally",
        "title_style": 'e.g. "Analytics Engineering Brief: [topic]"',
    },
    "Business Leader": {
        "audience": "a C-suite executive or business stakeholder with limited technical context",
        "emphasis": "business outcomes, customer-facing improvements, product value, and team momentum — avoid jargon and translate technical work into business impact",
        "language": "plain English, business-focused — no technical acronyms without explanation",
        "title_style": 'e.g. "Tech Team Update: [topic]"',
    },
}


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
                response_mime_type="application/json",
                response_schema=_DIGEST_SCHEMA,
            ),
        )
        return json.loads(response.text)
    except Exception as e:
        print(f"Summarization failed with Gemini 3: {e}")
        print(f"Raw response text: {response.text if response else 'no response'}")
        return None


def auto_snitch_with_gemini(mrs_data):
    if not mrs_data:
        return []

    mr_context = _build_mr_context(mrs_data)

    prompt = f"""
You are a Team Lead curating the agenda for a weekly analytics demo meeting. The goal of the demo is technical exposure and inspiration — attendees should walk away with new techniques and approaches in mind that they can apply to their own work.

Review these Merge Requests and select exactly ONE MR per author to highlight.

Rules:
- Include every author who submitted at least one MR — do not skip any author.
- Select the single BEST MR for each author: the one most likely to teach teammates something or spark curiosity about a technique.
- Assign a "spark score" from 1 to 10 reflecting how likely this MR is to inspire others or expose them to a new technique or approach:
  - 8-10: Novel technique, clever solution, or approach others could learn from and apply elsewhere
  - 5-7: Solid technical work that demonstrates good craft or an interesting pattern
  - 1-4: Routine or mechanical change with little to teach (still include — just score it low)

Good demo candidates (focus on the HOW, not the WHY):
- Clever or non-obvious technical approaches to a problem
- New tools, libraries, or patterns introduced to the codebase
- Refactors that demonstrate better ways to structure code
- Performance improvements that show interesting engineering tradeoffs
- Anything a teammate could look at and say "oh, I didn't know you could do it that way"

Poor demo candidates (score low, but still include if it's the author's only MR):
- Documentation-only changes
- Dependency bumps with no behavior change
- Configuration or environment file changes
- Trivial copy/text fixes or formatting-only changes

Output a strict JSON list of objects, one per author.
Each object must have the following keys:
- "author": The author's name
- "demo_title": A catchy title for the demo
- "description": A short blurb explaining what technique or approach is interesting and what others could learn from it.
- "song_recommendation": A song (Artist - Title) that loosely ties to the content of the demo.
- "link": The URL to the MR.
- "spark_score": An integer from 1 to 10 rating how likely this MR is to inspire or expose teammates to something new.

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
                response_mime_type="application/json",
                response_schema=_SNITCH_SCHEMA,
            ),
        )
        return json.loads(response.text)
    except Exception as e:
        print(f"Auto Snitch failed: {e}")
        print(f"Raw response text: {response.text if response else 'no response'}")
        return None


def generate_podcast_script(mrs_data, length_minutes, role, rate_percent):
    if not mrs_data:
        return None

    mr_context = _build_mr_context(mrs_data)
    word_count = int(_WORD_COUNT_TARGETS.get(length_minutes, 750) * (1 + rate_percent / 100))

    framing = _ROLE_FRAMING.get(role)
    if framing:
        role_section = f"""
Audience & Tone:
- This episode is intended for {framing['audience']}
- Emphasize: {framing['emphasis']}
- Language style: {framing['language']}
- Title style: {framing['title_style']}
"""
    else:
        role_section = f"""
Audience & Tone:
- This episode is intended for: {role}
- Tailor the language, terminology, emphasis, and episode title to suit this specific audience
"""

    prompt = f"""
You are a podcast script writer. Write a script for a conversational two-host podcast covering recent engineering work.

Hosts:
- Alex: enthusiastic, asks great questions, synthesizes ideas
- Matt: technical expert, explains things clearly, adds color commentary
{role_section}
Guidelines:
- Target approximately {word_count} words total across all segments
- Do NOT read MR titles literally — rephrase them naturally in conversation
- No bullet lists; pure dialogue only — this will be spoken aloud
- Make it feel like a real podcast: banter, follow-up questions, brief tangents are welcome
- Each segment is one speaker saying one continuous thought (a few sentences)
- Alternate between Alex and Matt naturally
- Start with Alex welcoming listeners and introducing the episode topic
- End with Matt wrapping up

MR DATA:
{mr_context}
"""

    response = None
    try:
        response = _generate(
            prompt,
            types.GenerateContentConfig(
                temperature=0.7,
                top_p=0.95,
                top_k=40,
                response_mime_type="application/json",
                response_schema=_PODCAST_SCHEMA,
            ),
        )
        return json.loads(response.text)
    except Exception as e:
        print(f"Podcast script generation failed: {e}")
        print(f"Raw response: {response.text if response else 'no response'}")
        return None
