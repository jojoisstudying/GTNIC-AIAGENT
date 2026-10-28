"""B-Roll Asset Fetcher with local disk caching and fallback mechanisms."""

import os
import hashlib
import random
import shutil
import requests
from pathlib import Path
from typing import Optional, List, Dict, Any, Iterable

from src import config
from src.carousel.tools.pexels_client import PexelsClient

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
        # Ringkasan pemilihan klip terakhir (untuk event/log): source, query, reused
        self.last_info: Dict[str, Any] = {}
        self._fp_cache: Dict[tuple, Optional[str]] = {}

    def _fingerprint(self, path: Optional[str]) -> Optional[str]:
        """Identitas isi klip (ukuran + 64 KB pertama), supaya salinan `pexels_<id>.mp4` dan
        `<md5-query>.mp4` dikenali sebagai klip yang sama."""
        if not path:
            return None
        try:
            st = os.stat(path)
            key = (path, st.st_size, st.st_mtime_ns)
            if key not in self._fp_cache:
                with open(path, "rb") as f:
                    head = f.read(65536)
                self._fp_cache[key] = hashlib.md5(str(st.st_size).encode() + head).hexdigest()
            return self._fp_cache[key]
        except OSError:
            return None

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

    def _get_fallback_video(self, excluded: Optional[set] = None) -> Optional[str]:
        """Local fallback B-roll; klip yang belum dipakai scene lain didahulukan."""
        if not self.fallback_dir.exists():
            return None
        videos = sorted(self.fallback_dir.glob("*.mp4"))
        if not videos:
            return None
        excluded = excluded or set()
        for v in videos:
            if self._fingerprint(str(v)) not in excluded:
                return str(v)
        return str(videos[0])

    def _search_and_download(self, query: str, excluded: set) -> Optional[str]:
        """Cari `query` di Pexels, ambil klip pertama yang belum dipakai scene lain, simpan ke cache.

        Pexels mengurutkan hasil berdasarkan relevansi, jadi tiga teratas diacak (variasi) dan
        sisanya menyusul sebagai cadangan.
        """
        try:
            res = self.client.search_videos(query=query, per_page=8, orientation="portrait")
        except Exception:  # noqa: BLE001 - API down / rate limit: lanjut ke keyword berikutnya
            return None
        videos = list((res or {}).get("videos", []) or [])
        top = videos[:3]
        random.shuffle(top)
        for v in top + videos[3:]:
            download_url = self._select_best_video_file(v)
            if not download_url:
                continue
            v_id = v.get("id") or random.randint(1000, 999999)
            target = self.cache_dir / f"pexels_{v_id}.mp4"
            cached = target.exists() and target.stat().st_size > 1000
            if cached and self._fingerprint(str(target)) in excluded:
                continue  # sudah dipakai scene lain: tidak perlu diunduh ulang
            if not cached and not self._download_video(download_url, target):
                continue
            if self._fingerprint(str(target)) in excluded:
                continue
            query_file = self.cache_dir / f"{self._get_cache_key(query)}.mp4"
            if not query_file.exists():
                try:
                    shutil.copyfile(target, query_file)
                except Exception:  # noqa: BLE001
                    pass
            return str(target)
        return None

    def fetch_clip(
        self,
        queries: List[str],
        prefer_cache: bool = True,
        exclude: Optional[Iterable[str]] = None,
    ) -> Optional[str]:
        """Pilih klip B-roll untuk satu scene.

        `queries` diurutkan dari yang paling relevan. Tiap keyword dicoba berurutan: cache untuk
        keyword itu (jika `prefer_cache`), lalu pencarian Pexels. Keyword pertama yang berhasil menang,
        jadi cache lama milik keyword yang kurang relevan tidak lagi mengalahkan keyword utama.

        `exclude` berisi path klip yang sudah dipakai scene lain pada video yang sama; klip itu
        dilewati supaya tidak ada dua scene dengan visual yang sama. Bila semua kandidat sudah
        terpakai, klip bekas dipakai ulang daripada tanpa visual. `self.last_info` mencatat sumbernya.
        """
        excluded = {fp for fp in (self._fingerprint(p) for p in (exclude or [])) if fp}
        queries = [q for q in (queries or []) if q and q.strip()]
        self.last_info = {"source": None, "query": None, "reused": False}

        if not queries:
            clip = self._get_fallback_video(excluded)
            self.last_info.update(source="fallback" if clip else None, reused=self._fingerprint(clip) in excluded)
            return clip

        reusable: List[tuple] = []  # kandidat yang hanya terlewat karena sudah dipakai scene lain

        # 1. Per keyword (urut relevansi): cache keyword itu, lalu pencarian
        for q in queries:
            if prefer_cache:
                cached = self._find_cached_video(self._get_cache_key(q))
                if cached:
                    if self._fingerprint(cached) in excluded:
                        reusable.append((cached, q))
                    else:
                        self.last_info.update(source="cache", query=q)
                        return cached
            found = self._search_and_download(q, excluded)
            if found:
                self.last_info.update(source="pexels", query=q)
                return found

        # 2. Pexels gagal / offline: cache keyword mana pun yang belum terpakai
        for q in queries:
            cached = self._find_cached_video(self._get_cache_key(q))
            if cached:
                if self._fingerprint(cached) in excluded:
                    reusable.append((cached, q))
                else:
                    self.last_info.update(source="cache", query=q)
                    return cached

        # 3. Klip lokal bawaan yang belum terpakai
        fallback = self._get_fallback_video(excluded)
        if fallback and self._fingerprint(fallback) not in excluded:
            self.last_info.update(source="fallback")
            return fallback

        # 4. Semua sudah terpakai: pakai ulang yang paling relevan daripada tanpa visual
        if reusable:
            clip, q = reusable[0]
            self.last_info.update(source="cache", query=q, reused=True)
            return clip
        if fallback:
            self.last_info.update(source="fallback", reused=True)
            return fallback
        return None
