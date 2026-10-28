"""BGM: pilih track milik brand, atau sintesis otomatis per mood."""
import wave

import numpy as np

from src.reels.tools import bgm


def _read(path):
    with wave.open(str(path)) as w:
        sr, n = w.getframerate(), w.getnframes()
        data = np.frombuffer(w.readframes(n), dtype=np.int16) / 32768.0
    return sr, n, data


def test_synth_is_valid_audible_and_right_length_for_every_mood(tmp_path):
    for mood in bgm.MOODS:
        res = bgm.resolve_bgm_track(mood, 18.4, bgm_dir=tmp_path / "none", cache_dir=tmp_path)
        assert res["source"] == "synth" and res["mood"] == mood
        sr, n, data = _read(res["path"])
        assert abs(n / sr - 19.0) < 0.1                      # dibulatkan ke atas ke detik penuh
        assert not np.isnan(data).any()
        assert 0.1 < np.abs(data).max() <= 0.81              # terdengar, tidak clipping
        assert np.sqrt((data ** 2).mean()) > 0.02            # bukan keheningan


def test_synth_fades_in_and_out():
    import tempfile, pathlib
    d = pathlib.Path(tempfile.mkdtemp())
    res = bgm.resolve_bgm_track("corporate_minimal", 10, bgm_dir=d / "none", cache_dir=d)
    sr, n, data = _read(res["path"])
    assert np.abs(data[:200]).max() < 0.02 and np.abs(data[-200:]).max() < 0.02


def test_unknown_mood_falls_back_to_default_mood(tmp_path):
    res = bgm.resolve_bgm_track("mood_aneh", 10, bgm_dir=tmp_path / "none", cache_dir=tmp_path)
    assert res["mood"] == bgm.DEFAULT_MOOD


def test_user_track_wins_over_synth_and_default_is_shared(tmp_path):
    assets = tmp_path / "bgm"
    assets.mkdir()
    (assets / "default.mp3").write_bytes(b"x" * 5000)
    res = bgm.resolve_bgm_track("energetic_tech", 10, bgm_dir=assets, cache_dir=tmp_path / "c")
    assert res["source"] == "file" and res["path"].endswith("default.mp3")

    (assets / "energetic_tech.wav").write_bytes(b"x" * 5000)
    res = bgm.resolve_bgm_track("energetic_tech", 10, bgm_dir=assets, cache_dir=tmp_path / "c")
    assert res["path"].endswith("energetic_tech.wav")      # file khusus mood lebih prioritas


def test_synth_is_cached_and_reused(tmp_path):
    a = bgm.resolve_bgm_track("inspiring_ambient", 12, bgm_dir=tmp_path / "none", cache_dir=tmp_path)
    mtime = (tmp_path / "inspiring_ambient_12s.wav").stat().st_mtime_ns
    b = bgm.resolve_bgm_track("inspiring_ambient", 12, bgm_dir=tmp_path / "none", cache_dir=tmp_path)
    assert a["path"] == b["path"]
    assert (tmp_path / "inspiring_ambient_12s.wav").stat().st_mtime_ns == mtime


def test_failure_returns_none_instead_of_raising(tmp_path):
    blocker = tmp_path / "bukan_folder"
    blocker.write_text("file biasa")
    assert bgm.resolve_bgm_track("corporate_minimal", 10, bgm_dir=tmp_path / "none", cache_dir=blocker / "x") is None
