"""Unit and integration test for Video Compositor assembly."""

import os
import wave
import numpy as np
import pytest
from src.reels.models import SceneSpec, WordTiming
from src.reels.tools.compositor import assemble_single_scene, assemble_full_video


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


# ----------------------------------------------------------------------------
# Transisi per scene, BGM, dan jeda hening setelah voiceover
# ----------------------------------------------------------------------------
def _scene(i, role, transition):
    return SceneSpec(scene_index=i, role=role, narration="Tes narasi singkat", search_keywords=["x"],
                     headline_overlay="TES", transition=transition)


def _scene_data(spec, audio, dur):
    return {"scene_spec": spec, "broll_path": None, "voiceover_path": audio,
            "word_timings": [WordTiming(word="Tes", start_ms=0, end_ms=400)], "duration_sec": dur}


def test_scene_keeps_silent_tail_after_voiceover(tmp_path):
    """Durasi scene tidak lagi dipotong mengikuti audio: jeda 0,3 detik jadi napas dan ruang crossfade."""
    audio = create_dummy_wav(str(tmp_path / "v.wav"), duration_sec=1.0)
    clip = assemble_single_scene(_scene(1, "hook", "none"), None, audio, [], 1.3)
    assert clip.duration == pytest.approx(1.3, abs=0.01)
    assert clip.audio.duration == pytest.approx(1.0, abs=0.05)
    clip.close()


def test_assemble_full_video_with_transitions_and_bgm(tmp_path):
    from moviepy import VideoFileClip
    from src.reels.tools.bgm import resolve_bgm_track

    audio = create_dummy_wav(str(tmp_path / "v.wav"), duration_sec=1.0)
    bgm = resolve_bgm_track("corporate_minimal", 6, cache_dir=tmp_path / "bgm")["path"]
    scenes = [
        _scene_data(_scene(1, "hook", "crossfade"), audio, 1.3),   # overlap 0,25 ke scene 2
        _scene_data(_scene(2, "explanation", "fade"), audio, 1.3),  # dip hitam ke scene 3 (tanpa overlap)
        _scene_data(_scene(3, "cta", "none"), audio, 1.3),
    ]
    out = str(tmp_path / "t.mp4")
    warnings = []
    assemble_full_video(scenes, out_mp3_bgm_path=bgm, out_video_path=out, fps=15,
                        warn=lambda n, d: warnings.append(n))

    assert warnings == []
    clip = VideoFileClip(out)
    try:
        assert clip.duration == pytest.approx(3 * 1.3 - 0.25, abs=0.2)   # 3,65 detik
        assert clip.audio is not None
    finally:
        clip.close()


def test_crossfade_overlap_never_exceeds_silent_tail(tmp_path):
    """Suara dua scene tidak boleh bertabrakan: overlap <= jeda hening di akhir scene sebelumnya."""
    from moviepy import VideoFileClip

    audio = create_dummy_wav(str(tmp_path / "v.wav"), duration_sec=1.0)
    scenes = [_scene_data(_scene(1, "hook", "crossfade"), audio, 1.05),   # ekor hening hanya 0,05
              _scene_data(_scene(2, "cta", "none"), audio, 1.05)]
    out = str(tmp_path / "t2.mp4")
    assemble_full_video(scenes, out_video_path=out, fps=15)
    clip = VideoFileClip(out)
    try:
        assert clip.duration == pytest.approx(2 * 1.05 - 0.05, abs=0.2)
    finally:
        clip.close()


def test_broken_bgm_does_not_break_video_and_is_reported(tmp_path):
    audio = create_dummy_wav(str(tmp_path / "v.wav"), duration_sec=1.0)
    bad_bgm = tmp_path / "bgm.mp3"
    bad_bgm.write_bytes(b"ini bukan audio" * 200)
    out = str(tmp_path / "t3.mp4")
    warnings = []
    assemble_full_video([_scene_data(_scene(1, "hook", "none"), audio, 1.3)],
                        out_mp3_bgm_path=str(bad_bgm), out_video_path=out, fps=15,
                        warn=lambda n, d: warnings.append(n))
    assert os.path.getsize(out) > 1000
    assert "video_bgm_failed" in warnings   # dulu error ditelan diam-diam
