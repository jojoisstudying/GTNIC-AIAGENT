"""Unit tests for TTS engine module."""

import os
import pytest
from src.video.tts_engine import (
    estimate_word_timings_from_sentences,
    generate_voiceover_with_subtitles,
)
from src.video.models import WordTiming


def test_estimate_word_timings_from_sentences():
    sentence_events = [
        {
            "type": "SentenceBoundary",
            "offset": 1000000,     # 100 ms
            "duration": 20000000,  # 2000 ms -> end at 2100 ms
            "text": "Kenapa startup gagal?",
        }
    ]
    timings = estimate_word_timings_from_sentences(sentence_events)
    assert len(timings) == 3
    assert timings[0].word == "Kenapa"
    assert timings[0].start_ms == 100
    assert timings[-1].word == "gagal?"
    assert timings[-1].end_ms == 2100
    for t in timings:
        assert t.end_ms >= t.start_ms


def test_estimate_empty_sentence():
    assert estimate_word_timings_from_sentences([]) == []
    assert estimate_word_timings_from_sentences([{"text": "   "}]) == []


@pytest.mark.asyncio
async def test_generate_voiceover_empty_text(tmp_path):
    out_mp3 = tmp_path / "empty.mp3"
    with pytest.raises(ValueError):
        await generate_voiceover_with_subtitles("", str(out_mp3))


@pytest.mark.asyncio
async def test_generate_voiceover_live(tmp_path):
    out_mp3 = tmp_path / "test_voice.mp3"
    text = "Uji coba suara kecerdasan buatan."
    
    path, timings, total_ms = await generate_voiceover_with_subtitles(text, str(out_mp3))
    
    assert os.path.exists(path)
    assert os.path.getsize(path) > 1000  # valid audio file
    assert len(timings) >= 4
    assert total_ms > 500
    for t in timings:
        assert isinstance(t, WordTiming)
        assert t.end_ms >= t.start_ms
