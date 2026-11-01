"""Pemeriksaan kompatibilitas file video dengan Instagram Reels sebelum diunggah.

Instagram menolak (atau memproses diam-diam lalu gagal) video yang bukan H.264 + AAC, bukan yuv420p,
terlalu pendek/panjang, atau terlalu besar. Lebih baik ketahuan di sini daripada setelah upload.
"""
from __future__ import annotations

import os
import re
import subprocess
from typing import Dict, List, Optional

MIN_DURATION_SEC = 3.0
MAX_DURATION_SEC = 90.0
MAX_SIZE_MB = 95.0   # batas upload sinkron Cloudinary (~100 MB); batas Instagram jauh lebih longgar


def parse_streams(ffmpeg_info: str) -> Dict[str, Optional[str]]:
    """Ambil codec video/audio dan pixel format dari stderr `ffmpeg -i`."""
    v = re.search(r"Video:\s*([A-Za-z0-9_]+)[^\n]*", ffmpeg_info)
    a = re.search(r"Audio:\s*([A-Za-z0-9_]+)", ffmpeg_info)
    pix = None
    if v:
        m = re.search(r"\b(yuvj?\d{3}p\d*(?:le|be)?|nv12|rgb\d*|gbrp|bgr\d*)\b", v.group(0))
        pix = m.group(1) if m else None
    return {"video_codec": v.group(1).lower() if v else None,
            "audio_codec": a.group(1).lower() if a else None,
            "pix_fmt": pix}


def _probe(path: str) -> str:
    import imageio_ffmpeg  # dependensi yang sudah dipakai qc_video
    proc = subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-hide_banner", "-i", path],
                          stderr=subprocess.PIPE, stdout=subprocess.PIPE, text=True, timeout=15)
    return proc.stderr


def evaluate(props: Dict, streams: Dict[str, Optional[str]]) -> List[str]:
    """Bagian murni (tanpa I/O) supaya mudah diuji: daftar masalah dari sifat file."""
    problems: List[str] = []
    dur = float(props.get("duration_sec") or 0.0)
    if not MIN_DURATION_SEC <= dur <= MAX_DURATION_SEC:
        problems.append(f"durasi {dur:.1f} detik di luar batas Reels ({MIN_DURATION_SEC:.0f}-{MAX_DURATION_SEC:.0f} detik)")
    w, h = int(props.get("width") or 0), int(props.get("height") or 0)
    if w and h and w >= h:
        problems.append(f"video {w}x{h} bukan vertikal; Reels butuh 9:16")
    size = float(props.get("file_size_mb") or 0.0)
    if size > MAX_SIZE_MB:
        problems.append(f"ukuran {size:.1f} MB melebihi batas {MAX_SIZE_MB:.0f} MB")
    if not props.get("has_audio"):
        problems.append("video tanpa audio")
    vc, ac, pix = streams.get("video_codec"), streams.get("audio_codec"), streams.get("pix_fmt")
    if vc not in ("h264", "hevc"):
        problems.append(f"codec video '{vc or 'tidak terbaca'}' tidak didukung Instagram (butuh H.264/HEVC)")
    if props.get("has_audio") and ac != "aac":
        problems.append(f"codec audio '{ac or 'tidak terbaca'}' tidak didukung Instagram (butuh AAC)")
    if pix and pix not in ("yuv420p", "yuvj420p"):
        problems.append(f"pixel format '{pix}' bisa ditolak Instagram (butuh yuv420p)")
    return problems


def check_reel_compat(path: str) -> List[str]:
    """Daftar masalah (kosong = aman diunggah). Tidak pernah raise."""
    from src.reels.tools.qc_video import inspect_media_file
    if not path or not os.path.isfile(path):
        return [f"file video tidak ditemukan: {path}"]
    props = inspect_media_file(path)
    if "error" in props:
        return [str(props["error"])]
    try:
        streams = parse_streams(_probe(path))
    except Exception as e:  # noqa: BLE001 - tidak bisa probe: jangan blokir, tapi beri tahu
        return evaluate(props, {"video_codec": "h264", "audio_codec": "aac", "pix_fmt": None}) + \
               [f"codec tidak bisa diperiksa ({type(e).__name__}); pastikan H.264 + AAC"]
    return evaluate(props, streams)
