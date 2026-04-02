import os
import json
import math
import time
from datetime import datetime
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv(override=True)

_client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"), http_options={"timeout": 120000})
_MODEL = "gemini-3-flash-preview"
_AUTHORS_PER_BATCH = 10
_SNITCH_RETRY_DELAYS = [5, 10]

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
        required=["author", "demo_title", "description", "song_recommendation", "link", "spark_score"],
    ),
)

_RECAP_SCHEMA = types.Schema(
    type=types.Type.ARRAY,
    items=types.Schema(
        type=types.Type.OBJECT,
        properties={
            "author": types.Schema(type=types.Type.STRING),
            "url": types.Schema(type=types.Type.STRING),
            "description": types.Schema(type=types.Type.STRING),
        },
        required=["author", "url", "description"],
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


def _is_retryable(e: Exception) -> bool:
    s = str(e).lower()
    return "503" in str(e) or "timeout" in s or "timed out" in s or "deadline" in s


def _generate(prompt, config, retries=3, base_delay=2):
    """Call Gemini with exponential backoff on 503/timeout transient errors."""
    for attempt in range(retries):
        try:
            return _client.models.generate_content(
                model=_MODEL,
                contents=prompt,
                config=config,
            )
        except Exception as e:
            is_last = attempt == retries - 1
            if is_last or not _is_retryable(e):
                raise
            delay = base_delay * (2**attempt)
            print(f"Gemini transient error on attempt {attempt + 1}, retrying in {delay}s… ({e})")
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


_DIGEST_MAX_IMPACTFUL = 10
_DIGEST_MAX_TECHNICAL = 10


def _digest_batch(mrs_data, timeframe, max_impactful, max_technical, on_status=None, batch_label=""):
    """Run the digest Gemini call for a subset of MRs and return parsed results.

    Retries on 503/timeout errors using _SNITCH_RETRY_DELAYS.
    """
    current_date = datetime.now().strftime("%B %d, %Y")
    mr_context = _build_mr_context(mrs_data)

    prompt = f"""
You are a Technical Chief of Staff. Review these Merge Requests from the {timeframe}
and create an "Impact Digest" for a company executive.

Today's Date: {current_date}

The executive wants to see high-level progress and interesting technical wins.

Output a strict JSON object with the following keys:
- "executive_summary": 1-2 sentences on overall velocity for THIS batch of {len(mrs_data)} MRs.
- "impactful_changes": A list of objects (max {max_impactful}) focusing strictly on BUSINESS VALUE and USER IMPACT.
    - "title": A concise, business-friendly title summarizing the impact (do not use the raw MR title).
    - "description": A focus on the "Why" (business value).
    - "url": The MR URL.
    - "author": The MR Author's name.
    - "context_area": Inferred business area, application name, or technology (e.g. "Payments", "Frontend", "Infrastructure").
- "technical_highlights": A list of objects (up to {max_technical}) noting interesting architectural choices, refactors, or library updates.
    - "title": A short, specific title describing the technical change.
    - "description": Focus strictly on the "How" (engineering details). Do NOT repeat high-level features listed in "impactful_changes".
    - "url": The URL of the MR this change belongs to.
    - "author": The name of the author who made the change.

DATA:
{mr_context}
"""

    config = types.GenerateContentConfig(
        temperature=0.2,
        top_p=0.95,
        top_k=40,
        response_mime_type="application/json",
        response_schema=_DIGEST_SCHEMA,
    )
    attempts = len(_SNITCH_RETRY_DELAYS) + 1
    response = None
    for attempt in range(attempts):
        if on_status and attempt > 0:
            on_status(f"{batch_label} — retrying (attempt {attempt + 1}/{attempts})…")
        try:
            response = _client.models.generate_content(
                model=_MODEL, contents=prompt, config=config
            )
            return json.loads(response.text)
        except Exception as e:
            is_last = attempt == attempts - 1
            if is_last or not _is_retryable(e):
                print(f"Digest batch failed: {e}")
                print(f"Raw response text: {response.text if response else 'no response'}")
                return None
            delay = _SNITCH_RETRY_DELAYS[attempt]
            print(f"Digest transient error on attempt {attempt + 1}, retrying in {delay}s… ({e})")
            for remaining in range(delay, 0, -1):
                if on_status:
                    on_status(
                        f"{batch_label} — transient error, retrying in {remaining}s…"
                    )
                time.sleep(1)


def _merge_digest_batches(batch_results, timeframe, total_mrs, on_status=None):
    """Merge multiple batch digest results into one final digest via Gemini."""
    batch_summaries = json.dumps(batch_results, indent=2)

    prompt = f"""
You are a Technical Chief of Staff. You have been given multiple partial digest results from different batches of Merge Requests covering the {timeframe}. Merge them into a single cohesive executive digest.

Total MRs across all batches: {total_mrs}

Rules:
- "executive_summary": Write 1-2 fresh sentences on overall velocity. Mention that {total_mrs} MRs were merged. Synthesize themes across all batches.
- "impactful_changes": Select the top {_DIGEST_MAX_IMPACTFUL} most impactful changes across all batches. Keep the original url, author, and context_area. You may rewrite title and description for cohesion.
- "technical_highlights": Select the top {_DIGEST_MAX_TECHNICAL} most interesting technical highlights across all batches. Keep the original url and author. You may rewrite title and description for cohesion.

Do NOT invent new items — only select and refine from the provided batch results.

BATCH RESULTS:
{batch_summaries}
"""

    if on_status:
        on_status("Merging batch results into final digest…")

    config = types.GenerateContentConfig(
        temperature=0.2,
        top_p=0.95,
        top_k=40,
        response_mime_type="application/json",
        response_schema=_DIGEST_SCHEMA,
    )
    attempts = len(_SNITCH_RETRY_DELAYS) + 1
    response = None
    for attempt in range(attempts):
        try:
            response = _client.models.generate_content(
                model=_MODEL, contents=prompt, config=config
            )
            return json.loads(response.text)
        except Exception as e:
            is_last = attempt == attempts - 1
            if is_last or not _is_retryable(e):
                print(f"Digest merge failed: {e}")
                print(f"Raw response text: {response.text if response else 'no response'}")
                return None
            delay = _SNITCH_RETRY_DELAYS[attempt]
            print(f"Digest merge transient error on attempt {attempt + 1}, retrying in {delay}s… ({e})")
            for remaining in range(delay, 0, -1):
                if on_status:
                    on_status(f"Merge step — transient error, retrying in {remaining}s…")
                time.sleep(1)


def summarize_with_gemini(mrs_data, timeframe, on_batch_complete=None, on_status=None):
    if not mrs_data:
        return {}

    by_author = {}
    for mr in mrs_data:
        by_author.setdefault(mr["author"], []).append(mr)

    authors = list(by_author.keys())
    total_batches = math.ceil(len(authors) / _AUTHORS_PER_BATCH)

    # Distribute per-batch limits so totals approximate the final maximums
    max_impactful = max(1, math.ceil(_DIGEST_MAX_IMPACTFUL / total_batches))
    max_technical = max(1, math.ceil(_DIGEST_MAX_TECHNICAL / total_batches))

    # Single batch — skip the merge step
    if total_batches == 1:
        if on_status:
            on_status("Analyzing MRs…")
        result = _digest_batch(
            mrs_data, timeframe, _DIGEST_MAX_IMPACTFUL, _DIGEST_MAX_TECHNICAL,
            on_status=on_status, batch_label="Batch 1/1",
        )
        if on_batch_complete:
            on_batch_complete(1, 1)
        return result

    # Multiple batches — collect partial results, then merge
    total_steps = total_batches + 1  # +1 for the merge step
    batch_results = []
    for batch_num, i in enumerate(range(0, len(authors), _AUTHORS_PER_BATCH), start=1):
        batch_authors = set(authors[i : i + _AUTHORS_PER_BATCH])
        batch_mrs = [mr for mr in mrs_data if mr["author"] in batch_authors]
        batch_label = f"Batch {batch_num}/{total_batches}"
        print(f"Digest: processing {batch_label} ({len(batch_authors)} authors, {len(batch_mrs)} MRs)")
        if on_status:
            on_status(f"Analyzing {batch_label}…")
        batch_result = _digest_batch(
            batch_mrs, timeframe, max_impactful, max_technical,
            on_status=on_status, batch_label=batch_label,
        )
        if batch_result:
            batch_results.append(batch_result)
        else:
            print(f"Digest: {batch_label} returned no results, continuing")
        if on_batch_complete:
            on_batch_complete(batch_num, total_steps)

    if not batch_results:
        return None

    # Final merge pass
    print(f"Digest: merging {len(batch_results)} batch results")
    merged = _merge_digest_batches(batch_results, timeframe, len(mrs_data), on_status=on_status)
    if on_batch_complete:
        on_batch_complete(total_steps, total_steps)
    return merged


def _snitch_batch(mrs_data, on_status=None, batch_label=""):
    """Run the auto-snitch Gemini call for a subset of MRs and return parsed results.

    Retries on 503 errors using _SNITCH_RETRY_DELAYS, showing a per-second countdown
    via on_status if provided.
    """
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

    config = types.GenerateContentConfig(
        temperature=0.4,
        top_p=0.95,
        top_k=40,
        response_mime_type="application/json",
        response_schema=_SNITCH_SCHEMA,
    )
    attempts = len(_SNITCH_RETRY_DELAYS) + 1
    response = None
    for attempt in range(attempts):
        if on_status and attempt > 0:
            on_status(f"{batch_label} — retrying (attempt {attempt + 1}/{attempts})…")
        try:
            response = _client.models.generate_content(
                model=_MODEL, contents=prompt, config=config
            )
            return json.loads(response.text)
        except Exception as e:
            is_last = attempt == attempts - 1
            if is_last or not _is_retryable(e):
                print(f"Auto Snitch batch failed: {e}")
                print(f"Raw response text: {response.text if response else 'no response'}")
                return None
            delay = _SNITCH_RETRY_DELAYS[attempt]
            print(f"Auto Snitch transient error on attempt {attempt + 1}, retrying in {delay}s… ({e})")
            for remaining in range(delay, 0, -1):
                if on_status:
                    on_status(
                        f"{batch_label} — transient error, retrying in {remaining}s…"
                    )
                time.sleep(1)


def auto_snitch_with_gemini(mrs_data, on_batch_complete=None, on_status=None):
    if not mrs_data:
        return []

    by_author = {}
    for mr in mrs_data:
        by_author.setdefault(mr["author"], []).append(mr)

    authors = list(by_author.keys())
    total_batches = math.ceil(len(authors) / _AUTHORS_PER_BATCH)

    all_results = []
    for batch_num, i in enumerate(range(0, len(authors), _AUTHORS_PER_BATCH), start=1):
        batch_authors = set(authors[i : i + _AUTHORS_PER_BATCH])
        batch_mrs = [mr for mr in mrs_data if mr["author"] in batch_authors]
        batch_label = f"Batch {batch_num}/{total_batches}"
        print(f"Auto Snitch: processing {batch_label} ({len(batch_authors)} authors)")
        if on_status:
            on_status(f"Analyzing {batch_label}…")
        batch_results = _snitch_batch(batch_mrs, on_status=on_status, batch_label=batch_label)
        if batch_results:
            all_results.extend(batch_results)
        else:
            print(f"Auto Snitch: {batch_label} returned no results, continuing")
        if on_batch_complete:
            on_batch_complete(batch_num, total_batches)

    return all_results


def _recap_batch(mrs_data, on_status=None, batch_label=""):
    """Run the contributor recap Gemini call for a subset of MRs and return parsed results.

    Retries on 503 errors using _SNITCH_RETRY_DELAYS, showing a per-second countdown
    via on_status if provided.
    """
    mr_context = _build_mr_context(mrs_data)

    prompt = f"""
You are a Technical Chief of Staff writing a contributor recap for an engineering team.

For EVERY merge request in the data below, produce exactly one entry describing the technical work done.

Rules:
- Include ALL merge requests — do not skip any.
- Use the exact author name and URL from the data — do not modify them.
- Write 1–2 short sentences (~30 words max total) focusing on HOW the change was implemented — the technical approach, pattern, or method used. Weave in which product, app, or repo the change belongs to naturally within the description.
- Do NOT explain why the change was made or its business value. Focus on engineering technique and context.
- Keep descriptions concrete and specific (e.g. "Replaced the auth service's linear token scan with a binary search" not "Improved performance").

Output a strict JSON list, one object per MR with keys: "author", "url", "description".

DATA:
{mr_context}
"""

    config = types.GenerateContentConfig(
        temperature=0.2,
        top_p=0.95,
        top_k=40,
        response_mime_type="application/json",
        response_schema=_RECAP_SCHEMA,
    )
    attempts = len(_SNITCH_RETRY_DELAYS) + 1
    response = None
    for attempt in range(attempts):
        if on_status and attempt > 0:
            on_status(f"{batch_label} — retrying (attempt {attempt + 1}/{attempts})…")
        try:
            response = _client.models.generate_content(
                model=_MODEL, contents=prompt, config=config
            )
            return json.loads(response.text)
        except Exception as e:
            is_last = attempt == attempts - 1
            if is_last or not _is_retryable(e):
                print(f"Contributor recap batch failed: {e}")
                print(f"Raw response text: {response.text if response else 'no response'}")
                return None
            delay = _SNITCH_RETRY_DELAYS[attempt]
            print(f"Contributor recap transient error on attempt {attempt + 1}, retrying in {delay}s… ({e})")
            for remaining in range(delay, 0, -1):
                if on_status:
                    on_status(
                        f"{batch_label} — transient error, retrying in {remaining}s…"
                    )
                time.sleep(1)


def contributor_recap_with_gemini(mrs_data, on_batch_complete=None, on_status=None):
    if not mrs_data:
        return []

    by_author = {}
    for mr in mrs_data:
        by_author.setdefault(mr["author"], []).append(mr)

    authors = list(by_author.keys())
    total_batches = math.ceil(len(authors) / _AUTHORS_PER_BATCH)

    all_results = []
    for batch_num, i in enumerate(range(0, len(authors), _AUTHORS_PER_BATCH), start=1):
        batch_authors = set(authors[i : i + _AUTHORS_PER_BATCH])
        batch_mrs = [mr for mr in mrs_data if mr["author"] in batch_authors]
        batch_label = f"Batch {batch_num}/{total_batches}"
        print(f"Contributor recap: processing {batch_label} ({len(batch_authors)} authors)")
        if on_status:
            on_status(f"Analyzing {batch_label}…")
        batch_results = _recap_batch(batch_mrs, on_status=on_status, batch_label=batch_label)
        if batch_results:
            all_results.extend(batch_results)
        else:
            print(f"Contributor recap: {batch_label} returned no results, continuing")
        if on_batch_complete:
            on_batch_complete(batch_num, total_batches)

    return all_results


def generate_lyria_prompt(mr: dict, genre: str, mood: str, tempo: str) -> str:
    """Generate a Lyria-optimized music description from an MR and user controls."""
    prompt = f"""You are a music director writing a brief for an AI music generator.

Based on the merge request below, write a single vivid paragraph (2-3 sentences) describing a piece of music that captures the essence of this technical work. The music should be {genre} in genre, {mood} in mood, and {tempo} in tempo.

MR Title: {mr.get('title', '')}
Repo: {mr.get('repo', '')}
Description: {mr.get('description', '')[:400]}

Write only the music description — no preamble, no explanation. Be specific about instruments, texture, and energy. Do not mention code or software."""

    response = _generate(prompt, types.GenerateContentConfig(temperature=0.8))
    return response.text.strip()


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
- Do NOT reference a specific time period (e.g. "this week", "this month") — the data may cover any range; refer to it simply as "recent work" or "the work we're covering today"
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
