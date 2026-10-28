"""Unit and integration tests for B-Roll fetcher and Pexels client."""

import pytest
from unittest.mock import MagicMock, patch
from src.carousel.tools.pexels_client import PexelsClient
from src.reels.tools.broll_fetcher import BRollFetcher


def test_pexels_client_no_key():
    client = PexelsClient(api_key="")
    res = client.search_videos("business meeting")
    assert res.get("total_results") == 0
    assert "PEXELS_API_KEY is not set" in res.get("error", "")


@patch("src.carousel.tools.pexels_client.requests.get")
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


@patch("src.reels.tools.broll_fetcher.requests.get")
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


# ----------------------------------------------------------------------------
# Relevansi & deduplikasi antar scene
# ----------------------------------------------------------------------------
def _video(vid, link="https://fake.url/{}.mp4"):
    return {"id": vid, "video_files": [{"height": 1920, "width": 1080, "link": link.format(vid)}]}


def _clip(path, tag: bytes):
    path.write_bytes(tag * 2000)  # >1000 byte, isi unik per klip
    return path


def test_first_keyword_search_beats_cache_of_a_later_keyword(tmp_path):
    """E: cache lama milik keyword kedua tidak boleh mengalahkan keyword utama (paling relevan)."""
    cache = tmp_path / "cache"
    cache.mkdir()
    client = MagicMock()
    client.search_videos.return_value = {"videos": [_video(1)]}
    fetcher = BRollFetcher(pexels_client=client, cache_dir=cache, fallback_dir=tmp_path / "fb")
    stale = _clip(cache / f"{fetcher._get_cache_key('generic stuff')}.mp4", b"STALE")

    with patch.object(fetcher, "_download_video", side_effect=lambda url, out: out.write_bytes(b"NEW" * 2000) or True):
        path = fetcher.fetch_clip(["padlock browser address bar", "generic stuff"])

    assert path != str(stale)
    assert path.endswith("pexels_1.mp4")
    assert fetcher.last_info["source"] == "pexels" and fetcher.last_info["query"] == "padlock browser address bar"
    client.search_videos.assert_called_once()


def test_cache_for_the_same_keyword_is_still_used_without_network(tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    client = MagicMock()
    fetcher = BRollFetcher(pexels_client=client, cache_dir=cache, fallback_dir=tmp_path / "fb")
    hit = _clip(cache / f"{fetcher._get_cache_key('server room cables')}.mp4", b"HIT")
    assert fetcher.fetch_clip(["server room cables", "x"]) == str(hit)
    client.search_videos.assert_not_called()
    assert fetcher.last_info == {"source": "cache", "query": "server room cables", "reused": False}


def test_exclude_skips_clip_already_used_by_another_scene(tmp_path):
    """E: dua scene tidak boleh mendapat klip yang sama."""
    cache = tmp_path / "cache"
    cache.mkdir()
    client = MagicMock()
    client.search_videos.return_value = {"videos": [_video(1), _video(2)]}
    fetcher = BRollFetcher(pexels_client=client, cache_dir=cache, fallback_dir=tmp_path / "fb")
    first = _clip(cache / "pexels_1.mp4", b"ONE")
    _clip(cache / "pexels_2.mp4", b"TWO")

    with patch("src.reels.tools.broll_fetcher.random.shuffle", lambda x: None):
        path = fetcher.fetch_clip(["office"], exclude=[str(first)])
    assert path.endswith("pexels_2.mp4")


def test_exclude_recognises_the_md5_copy_of_the_same_clip(tmp_path):
    """Salinan `<md5-query>.mp4` dan `pexels_<id>.mp4` adalah klip yang sama (dikenali lewat isi)."""
    cache = tmp_path / "cache"
    cache.mkdir()
    fetcher = BRollFetcher(pexels_client=MagicMock(), cache_dir=cache, fallback_dir=tmp_path / "fb")
    original = _clip(cache / "pexels_7.mp4", b"SAME")
    copy = cache / f"{fetcher._get_cache_key('same topic')}.mp4"
    copy.write_bytes(original.read_bytes())
    fetcher.client.search_videos.return_value = {"videos": []}

    other = _clip(tmp_path / "fb" / "other.mp4", b"OTHER")
    path = fetcher.fetch_clip(["same topic"], exclude=[str(original)])
    assert path == str(other)  # md5-copy dilewati karena isinya = klip yang sudah dipakai


def test_reuses_a_used_clip_when_nothing_else_exists(tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    client = MagicMock()
    client.search_videos.return_value = {"videos": []}
    fetcher = BRollFetcher(pexels_client=client, cache_dir=cache, fallback_dir=tmp_path / "fb")
    only = _clip(cache / f"{fetcher._get_cache_key('only one')}.mp4", b"ONLY")
    assert fetcher.fetch_clip(["only one"], exclude=[str(only)]) == str(only)
    assert fetcher.last_info["reused"] is True
