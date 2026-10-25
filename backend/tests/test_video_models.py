"""Unit tests for video system Pydantic models."""

import pytest
from pydantic import ValidationError
from src.video.models import WordTiming, SceneSpec, VideoScriptSchema, VideoRunResult


def test_word_timing_valid():
    wt = WordTiming(word="Halo", start_ms=0, end_ms=350)
    assert wt.word == "Halo"
    assert wt.start_ms == 0
    assert wt.end_ms == 350


def test_word_timing_negative_validation():
    with pytest.raises(ValidationError):
        WordTiming(word="Halo", start_ms=-10, end_ms=200)


def test_scene_spec_valid():
    scene = SceneSpec(
        scene_index=1,
        role="hook",
        narration="Kenapa 80 persen startup gulung tikar?",
        search_keywords=["startup failure", "stressed office"],
        headline_overlay="80% STARTUP GAGAL?",
        transition="fade"
    )
    assert scene.scene_index == 1
    assert scene.role == "hook"
    assert len(scene.search_keywords) == 2


def test_scene_spec_invalid_role():
    with pytest.raises(ValidationError):
        SceneSpec(
            scene_index=1,
            role="unknown_role",  # type: ignore
            narration="Valid narration here",
            search_keywords=["test"],
            headline_overlay="OVERLAY"
        )


def test_video_script_schema_valid():
    raw_data = {
        "topic": "Strategi Cashflow Bisnis 2026",
        "target_duration_sec": 30,
        "bgm_mood": "corporate_minimal",
        "scenes": [
            {
                "scene_index": 1,
                "role": "hook",
                "narration": "Kenapa 80 persen startup gulung tikar di tahun kedua?",
                "search_keywords": ["business failure meeting"],
                "headline_overlay": "80% STARTUP GAGAL?",
                "transition": "fade"
            },
            {
                "scene_index": 2,
                "role": "cta",
                "narration": "Simpan video ini dan follow untuk tips selanjutnya.",
                "search_keywords": ["modern office"],
                "headline_overlay": "SIMPAN & FOLLOW",
                "transition": "none"
            }
        ]
    }
    script = VideoScriptSchema.model_validate(raw_data)
    assert script.topic == "Strategi Cashflow Bisnis 2026"
    assert len(script.scenes) == 2
    assert script.target_duration_sec == 30


def test_video_script_schema_invalid_duration():
    with pytest.raises(ValidationError):
        VideoScriptSchema(
            topic="Test",
            target_duration_sec=120,  # Le 60
            scenes=[
                SceneSpec(
                    scene_index=1,
                    role="hook",
                    narration="Test hook",
                    search_keywords=["test"],
                    headline_overlay="HEADLINE"
                )
            ]
        )


def test_video_run_result():
    res = VideoRunResult(
        ok=True,
        video_path="output/reels/run_1.mp4",
        duration_sec=28.5,
        file_size_mb=12.4,
        scenes_count=3,
        issues=[]
    )
    assert res.ok is True
    assert res.video_path == "output/reels/run_1.mp4"
