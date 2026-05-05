from typing import Any

import httpx

from app.config import settings


class PixabayService:
    async def search_images(self, query: str, page: int, per_page: int) -> list[dict[str, Any]]:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(
                "https://pixabay.com/api/",
                params={
                    "key": settings.pixabay_api_key,
                    "q": query,
                    "page": page,
                    "per_page": per_page,
                    "image_type": "photo",
                    "safesearch": "true",
                    "lang": "en",
                },
            )
            response.raise_for_status()
            payload = response.json()

        results: list[dict[str, Any]] = []
        for item in payload.get("hits", []):
            results.append(
                {
                    "source_id": str(item.get("id")),
                    "source": "pixabay",
                    "asset_type": "image",
                    "url": item.get("largeImageURL") or item.get("webformatURL"),
                    "thumbnail_url": item.get("previewURL"),
                    "photographer": item.get("user"),
                    "width": item.get("imageWidth"),
                    "height": item.get("imageHeight"),
                }
            )
        return results

    async def search_videos(self, query: str, page: int, per_page: int) -> list[dict[str, Any]]:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(
                "https://pixabay.com/api/videos/",
                params={
                    "key": settings.pixabay_api_key,
                    "q": query,
                    "page": page,
                    "per_page": per_page,
                    "safesearch": "true",
                    "lang": "en",
                },
            )
            response.raise_for_status()
            payload = response.json()

        results: list[dict[str, Any]] = []
        for item in payload.get("hits", []):
            medium = item.get("videos", {}).get("medium", {})
            if not medium.get("url"):
                continue
            results.append(
                {
                    "source_id": str(item.get("id")),
                    "source": "pixabay",
                    "asset_type": "video",
                    "url": medium.get("url"),
                    "thumbnail_url": item.get("videos", {}).get("tiny", {}).get("thumbnail") or item.get("picture_id"),
                    "photographer": item.get("user"),
                    "width": medium.get("width"),
                    "height": medium.get("height"),
                }
            )
        return results
