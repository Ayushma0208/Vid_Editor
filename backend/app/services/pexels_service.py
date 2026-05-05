import asyncio
import time
from typing import Any

import httpx

from app.config import settings


class PexelsService:
    _rate_lock = asyncio.Lock()
    _request_timestamps: list[float] = []
    _hourly_limit = 200

    async def _respect_rate_limit(self) -> None:
        async with self._rate_lock:
            now = time.time()
            self._request_timestamps = [ts for ts in self._request_timestamps if (now - ts) < 3600]
            if len(self._request_timestamps) >= self._hourly_limit:
                raise RuntimeError("Pexels hourly rate limit reached")
            self._request_timestamps.append(now)

    async def search_photos(self, query: str, page: int, per_page: int) -> list[dict[str, Any]]:
        await self._respect_rate_limit()
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(
                "https://api.pexels.com/v1/search",
                params={"query": query, "page": page, "per_page": per_page},
                headers={"Authorization": settings.pexels_api_key},
            )
            response.raise_for_status()
            payload = response.json()

        results: list[dict[str, Any]] = []
        for item in payload.get("photos", []):
            results.append(
                {
                    "source_id": str(item.get("id")),
                    "source": "pexels",
                    "asset_type": "image",
                    "url": item.get("src", {}).get("original") or item.get("url"),
                    "thumbnail_url": item.get("src", {}).get("medium"),
                    "photographer": item.get("photographer"),
                    "width": item.get("width"),
                    "height": item.get("height"),
                }
            )
        return results

    async def search_videos(self, query: str, page: int, per_page: int) -> list[dict[str, Any]]:
        await self._respect_rate_limit()
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(
                "https://api.pexels.com/videos/search",
                params={"query": query, "page": page, "per_page": per_page},
                headers={"Authorization": settings.pexels_api_key},
            )
            response.raise_for_status()
            payload = response.json()

        results: list[dict[str, Any]] = []
        for item in payload.get("videos", []):
            medium_file = next(
                (video_file for video_file in item.get("video_files", []) if video_file.get("quality") == "sd"),
                None,
            )
            if not medium_file:
                medium_file = next(iter(item.get("video_files", [])), None)
            if not medium_file:
                continue
            image = item.get("image")
            results.append(
                {
                    "source_id": str(item.get("id")),
                    "source": "pexels",
                    "asset_type": "video",
                    "url": medium_file.get("link"),
                    "thumbnail_url": image,
                    "photographer": None,
                    "width": medium_file.get("width") or item.get("width"),
                    "height": medium_file.get("height") or item.get("height"),
                }
            )
        return results
