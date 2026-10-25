"""TTS Engine wrapper using edge-tts with word-level timing extraction and retry resilience."""

import os
import re
from typing import List, Tuple
import edge_tts
from tenacity import retry, stop_after_attempt, wait_exponential

from src.video.models import WordTiming

DEFAULT_VOICE = "id-ID-ArdiNeural"
DEFAULT_RATE = "+5%"


def estimate_word_timings_from_sentences(
    sentence_events: List[dict]
) -> List[WordTiming]:
    """
    Interpolate word-level timestamps from sentence boundary events.
    Offset and duration from edge-tts are in 100-nanosecond units (ticks),
    so dividing by 10,000 gives milliseconds.
    """
    word_timings: List[WordTiming] = []

    for event in sentence_events:
        offset_ticks = event.get("offset", 0)
        duration_ticks = event.get("duration", 0)
        text = event.get("text", "").strip()
        if not text:
            continue

        start_ms = int(offset_ticks / 10000)
        duration_ms = int(duration_ticks / 10000)
        end_ms = start_ms + duration_ms

        words = text.split()
        if not words:
            continue

        total_chars = sum(max(len(w), 1) for w in words)
        current_time = start_ms

        for idx, word in enumerate(words):
            if idx == len(words) - 1:
                # Ensure last word reaches exactly the sentence boundary end
                w_end = end_ms
            else:
                char_share = len(word) / total_chars
                w_dur = max(int(char_share * duration_ms), 50)
                w_end = min(current_time + w_dur, end_ms)

            word_timings.append(
                WordTiming(
                    word=word,
                    start_ms=current_time,
                    end_ms=w_end,
                )
            )
            current_time = w_end

    return word_timings


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    reraise=True,
)
async def generate_voiceover_with_subtitles(
    text: str,
    out_path: str,
    voice: str = DEFAULT_VOICE,
    rate: str = DEFAULT_RATE,
) -> Tuple[str, List[WordTiming], int]:
    """
    Generate an MP3 audio voiceover file and word timings using edge-tts.
    
    Returns:
        (out_path, list_of_word_timings, total_duration_ms)
    """
    clean_text = text.strip()
    if not clean_text:
        raise ValueError("Narration text cannot be empty.")

    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)

    communicate = edge_tts.Communicate(clean_text, voice=voice, rate=rate)

    sentence_events: List[dict] = []
    word_boundary_events: List[dict] = []
    audio_data = bytearray()

    async for chunk in communicate.stream():
        chunk_type = chunk.get("type")
        if chunk_type == "audio":
            audio_data.extend(chunk.get("data", b""))
        elif chunk_type == "WordBoundary":
            word_boundary_events.append(chunk)
        elif chunk_type == "SentenceBoundary":
            sentence_events.append(chunk)

    if not audio_data:
        raise RuntimeError("No audio data received from edge-tts service.")

    with open(out_path, "wb") as f:
        f.write(audio_data)

    # If WordBoundary events are available, use them directly
    if word_boundary_events:
        word_timings = [
            WordTiming(
                word=chunk.get("text", ""),
                start_ms=int(chunk.get("offset", 0) / 10000),
                end_ms=int((chunk.get("offset", 0) + chunk.get("duration", 0)) / 10000),
            )
            for chunk in word_boundary_events
            if chunk.get("text")
        ]
    elif sentence_events:
        word_timings = estimate_word_timings_from_sentences(sentence_events)
    else:
        # Fallback if no boundary events returned (approximate 250ms per word)
        words = clean_text.split()
        word_timings = []
        cur = 0
        for w in words:
            dur = max(len(w) * 50, 200)
            word_timings.append(WordTiming(word=w, start_ms=cur, end_ms=cur + dur))
            cur += dur

    total_duration_ms = word_timings[-1].end_ms if word_timings else 0
    return out_path, word_timings, total_duration_ms
