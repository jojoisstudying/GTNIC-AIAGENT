"""Kompatibilitas Reels: codec, durasi, orientasi, ukuran (bagian murni, tanpa ffmpeg)."""
from src.video import reel_check as rc

FFMPEG_OK = """Input #0, mov,mp4,m4a,3gp,3g2,mj2, from 'reels.mp4':
  Duration: 00:00:19.30, start: 0.000000, bitrate: 1234 kb/s
  Stream #0:0[0x1](und): Video: h264 (High) (avc1 / 0x31637661), yuv420p(progressive), 1080x1920 [SAR 1:1 DAR 9:16], 1100 kb/s, 30 fps, 30 tbr, 15360 tbn (default)
  Stream #0:1[0x2](und): Audio: aac (LC) (mp4a / 0x6134706D), 44100 Hz, stereo, fltp, 128 kb/s (default)
"""

GOOD = {"duration_sec": 19.3, "width": 1080, "height": 1920, "has_audio": True, "file_size_mb": 4.2}


def test_parse_streams_reads_codecs_and_pixel_format():
    s = rc.parse_streams(FFMPEG_OK)
    assert s == {"video_codec": "h264", "audio_codec": "aac", "pix_fmt": "yuv420p"}


def test_parse_streams_detects_non_420_and_other_codecs():
    info = FFMPEG_OK.replace("yuv420p(progressive)", "yuv444p10le(progressive)").replace("Audio: aac", "Audio: mp3")
    s = rc.parse_streams(info)
    assert s["pix_fmt"] == "yuv444p10le" and s["audio_codec"] == "mp3"


def test_parse_streams_handles_garbage():
    assert rc.parse_streams("tidak ada stream") == {"video_codec": None, "audio_codec": None, "pix_fmt": None}


def test_good_file_has_no_problems():
    assert rc.evaluate(GOOD, rc.parse_streams(FFMPEG_OK)) == []


def test_each_rule_reports_its_own_problem():
    streams = rc.parse_streams(FFMPEG_OK)
    assert any("durasi" in p for p in rc.evaluate({**GOOD, "duration_sec": 2.0}, streams))
    assert any("durasi" in p for p in rc.evaluate({**GOOD, "duration_sec": 120.0}, streams))
    assert any("vertikal" in p for p in rc.evaluate({**GOOD, "width": 1920, "height": 1080}, streams))
    assert any("ukuran" in p for p in rc.evaluate({**GOOD, "file_size_mb": 120.0}, streams))
    assert any("tanpa audio" in p for p in rc.evaluate({**GOOD, "has_audio": False}, streams))
    assert any("codec video" in p for p in rc.evaluate(GOOD, {**streams, "video_codec": "vp9"}))
    assert any("codec audio" in p for p in rc.evaluate(GOOD, {**streams, "audio_codec": "opus"}))
    assert any("yuv420p" in p for p in rc.evaluate(GOOD, {**streams, "pix_fmt": "yuv444p"}))


def test_missing_file_is_reported_not_raised(tmp_path):
    problems = rc.check_reel_compat(str(tmp_path / "tidak_ada.mp4"))
    assert problems and "tidak ditemukan" in problems[0]
