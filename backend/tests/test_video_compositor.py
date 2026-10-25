"""Unit and integration test for Video Compositor assembly."""

import os
import wave
import numpy as np
import pytest
from src.video.models import SceneSpec, WordTiming
from src.video.compositor import assemble_single_scene, assemble_full_video


def create_dummy_wav(path: str, duration_sec: float = 1.0) -> str:
    """Generate a tiny, valid PCM WAV file for audio tests."""
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    sample_rate = 22050
    n_samples = int(sample_rate * duration_sec)
    t = np.linspace(0, duration_sec, n_samples, endpoint=False)
    samples = (np.sin(2 * np.pi * 440 * t) * 16000).astype(np.int16)

    with wave.open(path, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(samples.tobytes())
    return path


def test_assemble_single_scene(tmp_path):
    fake_audio = str(tmp_path / "voice.wav")
    create_dummy_wav(fake_audio, duration_sec=1.5)

    scene = SceneSpec(
        scene_index=1,
        role="hook",
        narration="Kenapa 80 persen startup gagal?",
        search_keywords=["business failure"],
        headline_overlay="80% STARTUP GAGAL?",
    )
    timings = [
        WordTiming(word="Kenapa", start_ms=0, end_ms=300),
        WordTiming(word="80%", start_ms=300, end_ms=600),
        WordTiming(word="startup", start_ms=600, end_ms=900),
        WordTiming(word="gagal?", start_ms=900, end_ms=1200),
    ]

    comp_clip = assemble_single_scene(
        scene_spec=scene,
        broll_path=None,  # Tests solid navy fallback
        voiceover_path=fake_audio,
        word_timings=timings,
        scene_duration_sec=1.5,
    )
    assert comp_clip.duration == 1.5
    assert comp_clip.size == (1080, 1920)
    comp_clip.close()


def test_assemble_full_video_short(tmp_path):
    out_mp4 = str(tmp_path / "output_test.mp4")
    fake_audio = str(tmp_path / "voice.wav")
    create_dummy_wav(fake_audio, duration_sec=1.0)

    scene1 = SceneSpec(
        scene_index=1,
        role="hook",
        narration="Kenapa startup gagal?",
        search_keywords=["business"],
        headline_overlay="STARTUP GAGAL",
    )
    scene2 = SceneSpec(
        scene_index=2,
        role="cta",
        narration="Follow kami sekarang.",
        search_keywords=["office"],
        headline_overlay="FOLLOW SEKARANG",
    )

    scenes_data = [
        {
            "scene_spec": scene1,
            "broll_path": None,
            "voiceover_path": fake_audio,
            "word_timings": [WordTiming(word="Kenapa", start_ms=0, end_ms=400)],
            "duration_sec": 1.0,
        },
        {
            "scene_spec": scene2,
            "broll_path": None,
            "voiceover_path": fake_audio,
            "word_timings": [WordTiming(word="Follow", start_ms=0, end_ms=400)],
            "duration_sec": 1.0,
        },
    ]

    result_path = assemble_full_video(
        scenes_data=scenes_data,
        out_video_path=out_mp4,
        fps=15,  # Low FPS for fast test execution
    )

    assert os.path.exists(result_path)
    assert os.path.getsize(result_path) > 1000
