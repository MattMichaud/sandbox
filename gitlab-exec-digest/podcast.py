import asyncio
from concurrent.futures import ThreadPoolExecutor

import edge_tts

VOICE_HOST_A = "en-US-JennyNeural"   # Alex — enthusiast
VOICE_HOST_B = "en-US-GuyNeural"    # Matt — technical expert


async def _generate_segment_audio(text, voice, rate_percent):
    """Stream edge-tts audio bytes for one segment."""
    communicate = edge_tts.Communicate(text, voice, rate=f"+{rate_percent}%")
    audio_chunks = []
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            audio_chunks.append(chunk["data"])
    return b"".join(audio_chunks)


async def _generate_all_audio(segments, rate_percent):
    """Generate audio for all segments concurrently, preserving order."""
    tasks = []
    for seg in segments:
        speaker = seg.get("speaker", "Alex")
        voice = VOICE_HOST_A if speaker == "Alex" else VOICE_HOST_B
        tasks.append(_generate_segment_audio(seg.get("text", ""), voice, rate_percent))
    return await asyncio.gather(*tasks)


def generate_podcast_audio(script, rate_percent):
    """Sync wrapper: generate and concatenate MP3 audio for all segments."""
    segments = script.get("segments", [])
    if not segments:
        return None

    def _run():
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(_generate_all_audio(segments, rate_percent))
        finally:
            loop.close()

    with ThreadPoolExecutor(max_workers=1) as executor:
        audio_parts = executor.submit(_run).result()

    return b"".join(audio_parts)
