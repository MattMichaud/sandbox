import os
import time

from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

IMAGE_MODEL = "gemini-3-pro-image-preview"
TEXT_MODEL = "gemini-3-flash-preview"

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))


def markdown_to_image_prompt(plan_name: str, markdown: str, title_strength: str) -> str:
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

    response = client.models.generate_content(
        model=TEXT_MODEL,
        contents=(
            "You are a creative director tasked with visualising a software development plan.\n"
            f"{strength_instruction}\n\n"
            "Write a single, vivid image-generation prompt (max 150 words) that captures the essence "
            "of this plan as a visual metaphor. Focus on mood, theme, and key concepts — not literal "
            "code or text. Output only the prompt, nothing else.\n\n"
            f"{markdown}"
        ),
    )
    return response.text.strip()


def generate_image(prompt: str, status) -> bytes:
    """Call the image model with up to 2 retries on 503 errors."""
    delays = [2, 4]
    attempts = len(delays) + 1

    for attempt in range(attempts):
        try:
            response = client.models.generate_content(
                model=IMAGE_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_modalities=["TEXT", "IMAGE"],
                ),
            )
            for part in response.parts:
                if part.inline_data is not None:
                    return part.inline_data.data
            raise ValueError("No image part found in response.")

        except Exception as exc:
            is_503 = "503" in str(exc)
            if is_503 and attempt < len(delays):
                delay = delays[attempt]
                status.update(
                    label=f"Service unavailable — retrying in {delay}s "
                          f"(attempt {attempt + 2}/{attempts})…"
                )
                time.sleep(delay)
                status.update(label=f"Generating image (attempt {attempt + 2}/{attempts})…")
            else:
                raise
