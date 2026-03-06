import asyncio
import os
import struct

from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv(override=True)

_LYRIA_MODEL = "models/lyria-realtime-exp"
_SAMPLE_RATE = 48000
_CHANNELS = 2
_BITS_PER_SAMPLE = 16
# int16 stereo 48kHz = 192,000 bytes per second
_BYTES_PER_SECOND = _SAMPLE_RATE * _CHANNELS * (_BITS_PER_SAMPLE // 8)


def _build_wav_bytes(pcm_data: bytes) -> bytes:
    """Wrap raw int16 stereo PCM data in a RIFF/WAV container."""
    data_size = len(pcm_data)
    file_size = 36 + data_size
    byte_rate = _BYTES_PER_SECOND
    block_align = _CHANNELS * (_BITS_PER_SAMPLE // 8)
    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF",
        file_size,
        b"WAVE",
        b"fmt ",
        16,
        1,  # PCM
        _CHANNELS,
        _SAMPLE_RATE,
        byte_rate,
        block_align,
        _BITS_PER_SAMPLE,
        b"data",
        data_size,
    )
    return header + pcm_data


async def _stream_music(prompt: str, duration_seconds: int) -> bytes:
    """Connect to Lyria RealTime, collect PCM audio, return WAV bytes."""
    client = genai.Client(
        api_key=os.getenv("GEMINI_API_KEY"),
        http_options={"api_version": "v1alpha", "timeout": 120000},
    )
    target_bytes = duration_seconds * _BYTES_PER_SECOND
    chunks: list[bytes] = []
    collected = 0

    async with client.aio.live.music.connect(model=_LYRIA_MODEL) as session:
        await session.set_weighted_prompts(
            [types.WeightedPrompt(text=prompt, weight=1.0)]
        )
        await session.play()

        async for message in session.receive():
            sc = getattr(message, "server_content", None)
            if sc is None:
                continue
            for chunk in getattr(sc, "audio_chunks", None) or []:
                data = getattr(chunk, "data", chunk)
                chunks.append(data)
                collected += len(data)
            if collected >= target_bytes:
                break

    raw_pcm = b"".join(chunks)[:target_bytes]
    return _build_wav_bytes(raw_pcm)


def generate_song(prompt: str, duration_seconds: int = 30) -> bytes:
    """Generate a music clip from a text prompt. Returns WAV bytes."""
    return asyncio.run(_stream_music(prompt, duration_seconds))
