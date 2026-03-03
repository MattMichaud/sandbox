import os
import time

from dotenv import load_dotenv
from google import genai
from google.genai import errors as genai_errors
from google.genai import types

load_dotenv()

IMAGE_MODEL = "gemini-3-pro-image-preview"
FALLBACK_IMAGE_MODEL = "gemini-2.5-flash-image"
TEXT_MODEL = "gemini-3-flash-preview"
FALLBACK_TEXT_MODEL = "gemini-2.5-flash"

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))


def markdown_to_image_prompt(plan_name: str, markdown: str, title_strength: str, style: str | None, status) -> str:
    strength_instruction = {
        "Low": (
            f"The plan is named '{plan_name}', but treat that as background context only. "
            "Draw your creative inspiration primarily from the content of the plan below."
        ),
        "Medium": (
            f"The plan is named '{plan_name}'. Balance the name and the content equally — "
            "let both inform the visual metaphor."
        ),
        "High": (
            f"The plan is named '{plan_name}'. This name is the primary creative driver. "
            "Let it anchor the image concept; use the content below only as supporting detail."
        ),
    }[title_strength]

    style_instruction = f"The image must be rendered in {style} style. " if style else ""

    contents = (
        "You are a creative director tasked with visualising a software development plan.\n"
        f"{strength_instruction}\n\n"
        "Write a single, vivid image-generation prompt (max 150 words) that captures the essence "
        "of this plan as a visual metaphor. Focus on mood, theme, and key concepts — not literal "
        f"code or text. {style_instruction}Output only the prompt, nothing else.\n\n"
        f"{markdown}"
    )

    delays = [5, 10]
    attempts = len(delays) + 1

    for attempt in range(attempts):
        status.update(label=f"Step 1/2 — Generating image prompt — attempt {attempt + 1}/{attempts}…")
        try:
            response = client.models.generate_content(model=TEXT_MODEL, contents=contents)
            return response.text.strip()
        except genai_errors.ServerError as exc:
            if exc.code == 503:
                if attempt < len(delays):
                    delay = delays[attempt]
                    for remaining in range(delay, 0, -1):
                        status.update(
                            label=f"Step 1/2 — Attempt {attempt + 1}/{attempts} failed — "
                                  f"503 Service Unavailable. Retrying in {remaining}s…"
                        )
                        time.sleep(1)
                else:
                    status.update(label=f"Step 1/2 — Falling back to stable model ({FALLBACK_TEXT_MODEL})…")
                    response = client.models.generate_content(model=FALLBACK_TEXT_MODEL, contents=contents)
                    return response.text.strip()
            else:
                raise


def _try_generate_image(model: str, prompt: str) -> bytes:
    response = client.models.generate_content(
        model=model,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_modalities=["TEXT", "IMAGE"],
        ),
    )
    for part in response.parts:
        if part.inline_data is not None:
            return part.inline_data.data
    raise ValueError("No image part found in response.")


def generate_image(prompt: str, status, use_fallback: bool = False) -> bytes:
    """Call the image model with up to 2 retries on 503 errors, then fall back to stable model."""
    if use_fallback:
        status.update(label=f"Generating image ({FALLBACK_IMAGE_MODEL})…")
        return _try_generate_image(FALLBACK_IMAGE_MODEL, prompt)

    delays = [5, 10]
    attempts = len(delays) + 1

    for attempt in range(attempts):
        status.update(label=f"Generating image — attempt {attempt + 1}/{attempts}…")
        try:
            return _try_generate_image(IMAGE_MODEL, prompt)
        except genai_errors.ServerError as exc:
            if exc.code == 503:
                if attempt < len(delays):
                    delay = delays[attempt]
                    for remaining in range(delay, 0, -1):
                        status.update(
                            label=f"Attempt {attempt + 1}/{attempts} failed — "
                                  f"503 Service Unavailable. Retrying in {remaining}s…"
                        )
                        time.sleep(1)
                else:
                    status.update(label=f"Falling back to stable model ({FALLBACK_IMAGE_MODEL})…")
                    return _try_generate_image(FALLBACK_IMAGE_MODEL, prompt)
            else:
                raise
