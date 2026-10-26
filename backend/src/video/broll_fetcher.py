"""B-Roll Asset Fetcher with local disk caching and fallback mechanisms."""

import os
import hashlib
import requests
from pathlib import Path
from typing import Optional, List, Dict, Any

from src import config
from src.tools.pexels_client import PexelsClient

DEFAULT_CACHE_DIR = config.ROOT / "data" / "video_cache"
DEFAULT_FALLBACK_DIR = config.ROOT / "assets" / "default_brolls"


class BRollFetcher:
    """Fetches portrait B-Roll clips from Pexels, caching them locally by query hash."""

    def __init__(
        self,
        pexels_client: Optional[PexelsClient] = None,
        cache_dir: Optional[Path] = None,
        fallback_dir: Optional[Path] = None,
    ):
        self.client = pexels_client or PexelsClient()
        self.cache_dir = Path(cache_dir or DEFAULT_CACHE_DIR)
        self.fallback_dir = Path(fallback_dir or DEFAULT_FALLBACK_DIR)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.fallback_dir.mkdir(parents=True, exist_ok=True)

    def _get_cache_key(self, query: str) -> str:
        """Create MD5 hash based on sanitized query string."""
        normalized = query.strip().lower()
        return hashlib.md5(normalized.encode("utf-8")).hexdigest()

    def _find_cached_video(self, query_hash: str) -> Optional[str]:
        target = self.cache_dir / f"{query_hash}.mp4"
        if target.exists() and target.stat().st_size > 1000:
            return str(target)
        return None

    def _select_best_video_file(self, video_obj: Dict[str, Any]) -> Optional[str]:
        """
        Choose portrait video file link with MAX 1080p (prefer 1080x1920 or 720x1280).
        Explicitly skip 4K (height > 1920) to ensure fast rendering.
        """
        files = video_obj.get("video_files", [])
        if not files:
            return None

        # Filter portrait files (height >= width), limit max height <= 1920 to avoid slow 4K renders
        portrait_files = [
            f for f in files
            if (f.get("height") or 0) >= (f.get("width") or 0)
            and 720 <= (f.get("height") or 0) <= 1920
            and f.get("link")
        ]

        if not portrait_files:
            # Fallback to any portrait files
            portrait_files = [
                f for f in files
                if (f.get("height") or 0) >= (f.get("width") or 0) and f.get("link")
            ]

        # Prefer 1080p height first, then 720p
        candidate = sorted(
            portrait_files or files,
            key=lambda x: (x.get("height") or 0) if (x.get("height") or 0) <= 1920 else -1,
            reverse=True,
        )

        return candidate[0]["link"] if candidate else None

    def _download_video(self, url: str, out_path: Path) -> bool:
        """Stream video download to disk."""
        try:
            with requests.get(url, stream=True, timeout=20) as r:
                r.raise_for_status()
                with open(out_path, "wb") as f:
                    for chunk in r.iter_content(chunk_size=65536):
                        if chunk:
                            f.write(chunk)
            return out_path.exists() and out_path.stat().st_size > 1000
        except Exception:
            if out_path.exists():
                out_path.unlink()
            return False

    def _get_fallback_video(self) -> Optional[str]:
        """Return a local fallback B-roll if available in fallback_dir."""
        if not self.fallback_dir.exists():
            return None
        videos = list(self.fallback_dir.glob("*.mp4"))
        if videos:
            return str(videos[0])
        return None

    def fetch_clip(self, queries: List[str], prefer_cache: bool = True) -> Optional[str]:
        """
        Search through the list of queries, prioritizing cached videos if prefer_cache=True.
        If not in cache, query Pexels API and save to cache.
        """
        import random

        if not queries:
            return self._get_fallback_video()

        # 1. Check local cache first if prefer_cache is True
        if prefer_cache:
            for q in queries:
                q_hash = self._get_cache_key(q)
                cached = self._find_cached_video(q_hash)
                if cached:
                    return cached

        # 2. Query Pexels API for variety / fresh content
        for q in queries:
            try:
                res = self.client.search_videos(query=q, per_page=6, orientation="portrait")
                videos = res.get("videos", [])
                if videos:
                    # Randomize among the top portrait videos for fresh visuals
                    shuffled_candidates = list(videos)
                    random.shuffle(shuffled_candidates)
                    for v in shuffled_candidates:
                        download_url = self._select_best_video_file(v)
                        if download_url:
                            v_id = v.get("id") or random.randint(1000, 999999)
                            target_file = self.cache_dir / f"pexels_{v_id}.mp4"
                            query_target_file = self.cache_dir / f"{self._get_cache_key(q)}.mp4"

                            if target_file.exists() and target_file.stat().st_size > 1000:
                                return str(target_file)
                            if self._download_video(download_url, target_file):
                                # Also link or create copy for query hash to fulfill query cache contract
                                if not query_target_file.exists():
                                    try:
                                        import shutil
                                        shutil.copyfile(target_file, query_target_file)
                                    except Exception:
                                        pass
                                return str(target_file)
            except Exception:
                pass

        # 3. Fallback to existing cached queries if Pexels API rate-limited or offline
        for q in queries:
            q_hash = self._get_cache_key(q)
            cached = self._find_cached_video(q_hash)
            if cached:
                return cached

        # 4. Final local fallback
        return self._get_fallback_video()
