"""Unit tests for subtitle and kinetic typography builder."""

import numpy as np
from src.video.models import WordTiming
from src.video.subtitle_builder import (
    group_words_into_phrases,
    create_kinetic_subtitle_frame,
    create_headline_overlay_frame,
    hex_to_rgba,
    load_brand_tokens,
)


def test_hex_to_rgba():
    rgba = hex_to_rgba("#FFB400", alpha=200)
    assert rgba == (255, 180, 0, 200)

    # Fallback default
    assert hex_to_rgba("invalid") == (255, 255, 255, 255)


def test_load_brand_tokens():
    tokens = load_brand_tokens()
    assert isinstance(tokens, dict)
    assert "bg" in tokens or "accent" in tokens


def test_group_words_into_phrases():
    words = [
        WordTiming(word="Kenapa", start_ms=0, end_ms=300),
        WordTiming(word="80%", start_ms=300, end_ms=600),
        WordTiming(word="startup", start_ms=600, end_ms=1000),
        WordTiming(word="gagal?", start_ms=1000, end_ms=1500),
        WordTiming(word="Bukan", start_ms=1500, end_ms=1800),
        WordTiming(word="karena", start_ms=1800, end_ms=2100),
    ]
    phrases = group_words_into_phrases(words, max_words=4)
    # The first 4 words have punctuation 'gagal?' -> triggers phrase split
    assert len(phrases) == 2
    assert phrases[0][0] == 0
    assert phrases[0][1] == 1500
    assert len(phrases[0][2]) == 4
    assert len(phrases[1][2]) == 2


def test_group_words_empty():
    assert group_words_into_phrases([]) == []


def test_create_kinetic_subtitle_frame():
    words = [
        WordTiming(word="80%", start_ms=0, end_ms=300),
        WordTiming(word="Startup", start_ms=300, end_ms=600),
        WordTiming(word="Gagal", start_ms=600, end_ms=1000),
    ]
    # Active word is index 1 ("Startup")
    frame = create_kinetic_subtitle_frame(words, active_word_index=1)
    assert isinstance(frame, np.ndarray)
    assert frame.shape == (1920, 1080, 4)
    # Ensure there is non-transparent pixel content drawn
    assert frame[:, :, 3].max() > 0


def test_create_headline_overlay_frame():
    frame = create_headline_overlay_frame("80% STARTUP GAGAL?")
    assert isinstance(frame, np.ndarray)
    assert frame.shape == (1920, 1080, 4)
    assert frame[:, :, 3].max() > 0
