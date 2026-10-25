"""Pexels Video API HTTP Client with rate-limiting and error handling."""

import os
import time
import requests
from typing import Dict, Any, Optional
from src import config

PEXELS_API_URL = "https://api.pexels.com/videos/search"


class PexelsClient:
    """Client for querying the Pexels Videos API with portrait orientation."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key if api_key is not None else config.opt("PEXELS_API_KEY", "")
        self.last_call_time: float = 0.0
        self.min_interval_sec: float = 0.5  # Rate limit: max ~2 requests/second

    def _rate_limit(self) -> None:
        elapsed = time.time() - self.last_call_time
        if elapsed < self.min_interval_sec:
            time.sleep(self.min_interval_sec - elapsed)
        self.last_call_time = time.time()

    def search_videos(
        self,
        query: str,
        per_page: int = 5,
        orientation: str = "portrait",
        size: str = "medium",
    ) -> Dict[str, Any]:
        """
        Search for videos matching query on Pexels.
        Returns JSON dictionary response from Pexels API.
        """
        if not self.api_key:
            return {"videos": [], "total_results": 0, "error": "PEXELS_API_KEY is not set"}

        self._rate_limit()
        headers = {"Authorization": self.api_key}
        params = {
            "query": query,
            "per_page": per_page,
            "orientation": orientation,
            "size": size,
        }

        try:
            resp = requests.get(PEXELS_API_URL, headers=headers, params=params, timeout=12)
            if resp.status_code == 200:
                return resp.json()
            elif resp.status_code == 429:
                return {"videos": [], "total_results": 0, "error": "Rate limit exceeded (HTTP 429)"}
            else:
                return {
                    "videos": [],
                    "total_results": 0,
                    "error": f"Pexels API error HTTP {resp.status_code}: {resp.text}",
                }
        except Exception as e:
            return {"videos": [], "total_results": 0, "error": str(e)}
