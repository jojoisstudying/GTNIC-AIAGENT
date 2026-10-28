"""Unit tests for video QC guardrail module."""

from unittest.mock import patch
from src.reels.tools.qc_video import inspect_media_file, verify_video_quality


def test_qc_non_existent_file():
    res = verify_video_quality("/non/existent/path.mp4")
    assert res.ok is False
    assert any("does not exist" in issue for issue in res.issues)


@patch("src.reels.tools.qc_video.inspect_media_file")
@patch("os.path.exists")
def test_qc_valid_video(mock_exists, mock_inspect):
    mock_exists.return_value = True
    mock_inspect.return_value = {
        "width": 1080,
        "height": 1920,
        "duration_sec": 30.5,
        "has_audio": True,
        "file_size_mb": 14.2,
    }

    res = verify_video_quality(
        "dummy.mp4",
        target_duration_sec=30.0,
        tolerance_sec=3.0,
        max_size_mb=50.0,
    )
    assert res.ok is True
    assert res.duration_sec == 30.5
    assert res.file_size_mb == 14.2
    assert len(res.issues) == 0


@patch("src.reels.tools.qc_video.inspect_media_file")
@patch("os.path.exists")
def test_qc_invalid_resolution_and_missing_audio(mock_exists, mock_inspect):
    mock_exists.return_value = True
    mock_inspect.return_value = {
        "width": 1920,
        "height": 1080,  # Horizontal instead of portrait!
        "duration_sec": 30.0,
        "has_audio": False,  # Mute
        "file_size_mb": 5.0,
    }

    res = verify_video_quality("dummy.mp4")
    assert res.ok is False
    assert any("Invalid resolution" in i for i in res.issues)
    assert any("Missing audio stream" in i for i in res.issues)


@patch("src.reels.tools.qc_video.inspect_media_file")
@patch("os.path.exists")
def test_qc_file_too_large(mock_exists, mock_inspect):
    mock_exists.return_value = True
    mock_inspect.return_value = {
        "width": 1080,
        "height": 1920,
        "duration_sec": 30.0,
        "has_audio": True,
        "file_size_mb": 65.0,  # > 50MB
    }

    res = verify_video_quality("dummy.mp4", max_size_mb=50.0)
    assert res.ok is False
    assert any("exceeds maximum limit" in i for i in res.issues)


@patch("src.reels.tools.qc_video.inspect_media_file")
@patch("os.path.exists")
def test_qc_duration_deviation(mock_exists, mock_inspect):
    mock_exists.return_value = True
    mock_inspect.return_value = {
        "width": 1080,
        "height": 1920,
        "duration_sec": 45.0,  # Target is 30, diff = 15s > tolerance 4s
        "has_audio": True,
        "file_size_mb": 15.0,
    }

    res = verify_video_quality("dummy.mp4", target_duration_sec=30.0, tolerance_sec=4.0)
    assert res.ok is False
    assert any("deviates from target" in i for i in res.issues)
