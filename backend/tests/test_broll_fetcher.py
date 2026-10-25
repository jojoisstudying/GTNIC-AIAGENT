"""Unit and integration tests for B-Roll fetcher and Pexels client."""

import pytest
from unittest.mock import MagicMock, patch
from src.tools.pexels_client import PexelsClient
from src.video.broll_fetcher import BRollFetcher


def test_pexels_client_no_key():
    client = PexelsClient(api_key="")
    res = client.search_videos("business meeting")
    assert res.get("total_results") == 0
    assert "PEXELS_API_KEY is not set" in res.get("error", "")


@patch("src.tools.pexels_client.requests.get")
def test_pexels_client_mock_success(mock_get):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "page": 1,
        "per_page": 2,
        "total_results": 10,
        "videos": [
            {
                "id": 12345,
                "video_files": [
                    {"height": 1920, "width": 1080, "link": "https://example.com/video1.mp4"}
                ]
            }
        ]
    }
    mock_get.return_value = mock_resp

    client = PexelsClient(api_key="dummy_key")
    res = client.search_videos("business", per_page=2)
    assert res.get("total_results") == 10
    assert len(res.get("videos")) == 1
    assert res["videos"][0]["id"] == 12345


def test_broll_fetcher_cache_hit(tmp_path):
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    
    mock_client = MagicMock()
    fetcher = BRollFetcher(pexels_client=mock_client, cache_dir=cache_dir)
    
    # Pre-populate cache for "office work"
    q_hash = fetcher._get_cache_key("office work")
    fake_video = cache_dir / f"{q_hash}.mp4"
    fake_video.write_bytes(b"dummy video binary content " * 100)

    # Calling fetch_clip should return cached path without calling Pexels API
    clip_path = fetcher.fetch_clip(["office work"])
    assert clip_path == str(fake_video)
    mock_client.search_videos.assert_not_called()


@patch("src.video.broll_fetcher.requests.get")
def test_broll_fetcher_download_and_cache(mock_get, tmp_path):
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()

    # Mock video download response
    mock_download_resp = MagicMock()
    mock_download_resp.raise_for_status.return_value = None
    mock_download_resp.iter_content.return_value = [b"chunk data " * 100]
    mock_get.return_value.__enter__.return_value = mock_download_resp

    mock_client = MagicMock()
    mock_client.search_videos.return_value = {
        "videos": [
            {
                "id": 999,
                "video_files": [
                    {"height": 1920, "width": 1080, "link": "https://fake.url/portrait.mp4"}
                ]
            }
        ]
    }

    fetcher = BRollFetcher(pexels_client=mock_client, cache_dir=cache_dir)
    clip_path = fetcher.fetch_clip(["finance data"])

    assert clip_path is not None
    assert clip_path.endswith(".mp4")
    assert (cache_dir / f"{fetcher._get_cache_key('finance data')}.mp4").exists()


def test_broll_fetcher_fallback_when_empty(tmp_path):
    cache_dir = tmp_path / "cache"
    fallback_dir = tmp_path / "fallback"
    cache_dir.mkdir()
    fallback_dir.mkdir()

    # Create dummy fallback video
    fallback_file = fallback_dir / "default.mp4"
    fallback_file.write_bytes(b"fallback content" * 100)

    mock_client = MagicMock()
    mock_client.search_videos.return_value = {"videos": []}

    fetcher = BRollFetcher(
        pexels_client=mock_client,
        cache_dir=cache_dir,
        fallback_dir=fallback_dir
    )
    clip_path = fetcher.fetch_clip(["non_existent_query"])
    assert clip_path == str(fallback_file)
