"""Musik latar (BGM) untuk video: pilih file milik brand, atau buat sendiri bila belum ada.

Urutan pencarian untuk mood `m`:
1. `assets/bgm/<m>.(mp3|wav|m4a|ogg|aac)`  -> track pilihanmu (disarankan, kualitas terbaik)
2. `assets/bgm/default.(...)`               -> satu track untuk semua mood
3. Sintesis otomatis (numpy, tanpa lisensi / tanpa unduhan): pad + arpeggio lembut per mood,
   disimpan di `data/bgm_cache/<mood>_<detik>s.wav` dan dipakai ulang.

Track sintetis sengaja sederhana (alas musik di bawah suara, bukan lagu). Untuk hasil yang
lebih "jadi", taruh track berlisensi bebas di `assets/bgm/`.
"""
from __future__ import annotations

import math
import wave
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

from src import config

BGM_DIR = config.ROOT / "assets" / "bgm"
CACHE_DIR = config.ROOT / "data" / "bgm_cache"
AUDIO_EXTS = (".mp3", ".wav", ".m4a", ".ogg", ".aac")
SAMPLE_RATE = 22050

DEFAULT_MOOD = "corporate_minimal"

# Akor sebagai nomor MIDI. arp: pembagian ketukan untuk arpeggio (0 = mati); pulse: denyut bass per 1/8.
MOODS: Dict[str, Dict[str, Any]] = {
    "corporate_minimal": {
        "bpm": 84, "arp": 1, "pulse": False, "arp_gain": 0.16,
        "chords": [[48, 55, 59, 64], [45, 52, 55, 60], [41, 53, 57, 64], [43, 55, 59, 64]],
    },
    "energetic_tech": {
        "bpm": 110, "arp": 2, "pulse": True, "arp_gain": 0.20,
        "chords": [[45, 57, 60, 64], [41, 57, 60, 65], [48, 55, 60, 64], [43, 55, 59, 62]],
    },
    "inspiring_ambient": {
        "bpm": 72, "arp": 1, "pulse": False, "arp_gain": 0.12,
        "chords": [[50, 57, 62, 66], [47, 54, 59, 62], [43, 55, 59, 62], [45, 57, 61, 64]],
    },
    "dramatic_urgent": {
        "bpm": 100, "arp": 0, "pulse": True, "arp_gain": 0.0,
        "chords": [[38, 50, 53, 57], [34, 46, 53, 58], [43, 50, 55, 58], [45, 52, 57, 61]],
    },
}


def _freq(midi: float) -> float:
    return 440.0 * 2.0 ** ((midi - 69) / 12.0)


def _add(buf: np.ndarray, start: int, sig: np.ndarray) -> None:
    end = min(len(buf), start + len(sig))
    if end > start:
        buf[start:end] += sig[: end - start]


def _pad_note(freq: float, dur: float, attack: float, release: float) -> np.ndarray:
    n = int((dur + release) * SAMPLE_RATE)
    t = np.arange(n) / SAMPLE_RATE
    tone = (np.sin(2 * np.pi * freq * t)
            + 0.6 * np.sin(2 * np.pi * freq * 1.004 * t)      # sedikit detune = suara lebih lebar
            + 0.2 * np.sin(2 * np.pi * freq * 2 * t))
    env = np.minimum(1.0, t / max(attack, 1e-3))
    env *= np.clip((dur + release - t) / max(release, 1e-3), 0.0, 1.0)
    return tone * env


def _pluck(freq: float, dur: float = 0.5) -> np.ndarray:
    n = int(dur * SAMPLE_RATE)
    t = np.arange(n) / SAMPLE_RATE
    tone = np.sin(2 * np.pi * freq * t) + 0.3 * np.sin(2 * np.pi * freq * 2 * t)
    return tone * np.exp(-t * 7.0) * np.minimum(1.0, t / 0.005)


def _bass_pulse(freq: float, dur: float = 0.18) -> np.ndarray:
    n = int(dur * SAMPLE_RATE)
    t = np.arange(n) / SAMPLE_RATE
    return np.sin(2 * np.pi * freq * t) * np.exp(-t * 16.0) * np.minimum(1.0, t / 0.004)


def synthesize_bgm(mood: str, duration_sec: float, out_path: Path) -> Path:
    """Buat track WAV mono 16-bit sepanjang `duration_sec` (deterministik, tanpa unduhan)."""
    spec = MOODS.get(mood) or MOODS[DEFAULT_MOOD]
    total = max(float(duration_sec), 3.0)
    n_total = int(total * SAMPLE_RATE)
    buf = np.zeros(n_total + SAMPLE_RATE * 4, dtype=np.float64)

    beat = 60.0 / spec["bpm"]
    bar = 4 * beat
    n_bars = int(math.ceil(total / bar)) + 1
    for b in range(n_bars):
        chord = spec["chords"][b % len(spec["chords"])]
        start = int(b * bar * SAMPLE_RATE)
        for note in chord:  # pad
            _add(buf, start, 0.16 * _pad_note(_freq(note), bar, attack=min(0.9, bar / 3), release=min(1.2, bar / 2)))
        if spec["arp"]:  # arpeggio oktaf atas, 1 atau 2 not per ketuk
            steps = 4 * spec["arp"]
            for k in range(steps):
                note = chord[k % len(chord)] + 12
                at = start + int(k * (bar / steps) * SAMPLE_RATE)
                _add(buf, at, spec["arp_gain"] * _pluck(_freq(note)))
        if spec["pulse"]:  # denyut bass per 1/8
            for k in range(8):
                at = start + int(k * (bar / 8) * SAMPLE_RATE)
                _add(buf, at, 0.22 * _bass_pulse(_freq(chord[0])))

    audio = buf[:n_total]
    fade_in, fade_out = int(1.0 * SAMPLE_RATE), int(min(2.0, total / 3) * SAMPLE_RATE)
    audio[:fade_in] *= np.linspace(0.0, 1.0, fade_in)
    audio[-fade_out:] *= np.linspace(1.0, 0.0, fade_out)
    peak = float(np.max(np.abs(audio))) or 1.0
    pcm = (audio / peak * 0.8 * 32767).astype(np.int16)

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(out_path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(SAMPLE_RATE)
        wav.writeframes(pcm.tobytes())
    return out_path


def _find_user_track(mood: str, bgm_dir: Path) -> Optional[Path]:
    for stem in (mood, "default"):
        for ext in AUDIO_EXTS:
            p = bgm_dir / f"{stem}{ext}"
            if p.is_file() and p.stat().st_size > 1000:
                return p
    return None


def resolve_bgm_track(
    mood: Optional[str],
    duration_sec: float,
    *,
    bgm_dir: Optional[Path] = None,
    cache_dir: Optional[Path] = None,
) -> Optional[Dict[str, Any]]:
    """Kembalikan {"path", "source": "file"|"synth", "mood"} atau None bila gagal total."""
    mood = mood if mood in MOODS else DEFAULT_MOOD
    bgm_dir = Path(bgm_dir or BGM_DIR)
    cache_dir = Path(cache_dir or CACHE_DIR)

    user = _find_user_track(mood, bgm_dir)
    if user:
        return {"path": str(user), "source": "file", "mood": mood}

    secs = int(math.ceil(max(duration_sec, 3.0)))
    target = cache_dir / f"{mood}_{secs}s.wav"
    try:
        if not (target.exists() and target.stat().st_size > 1000):
            synthesize_bgm(mood, secs, target)
        return {"path": str(target), "source": "synth", "mood": mood}
    except Exception:  # noqa: BLE001 - BGM bersifat opsional, jangan menggagalkan video
        return None
