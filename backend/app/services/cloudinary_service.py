import asyncio
from pathlib import Path

import cloudinary.api
import cloudinary.uploader
import httpx
from aiofiles import open as aio_open

import app.cloudinary_client  # noqa: F401
from app.config import settings

_LARGE_VIDEO_BYTES = 10 * 1024 * 1024
_CHUNK_SIZE = 6 * 1024 * 1024


class CloudinaryService:
    def is_configured(self) -> bool:
        return bool(
            settings.cloudinary_cloud_name
            and settings.cloudinary_api_key
            and settings.cloudinary_api_secret
        )

    async def upload_video(self, file_path: str, folder: str) -> dict:
        if not self.is_configured():
            raise RuntimeError("Cloudinary is not configured")
        size = Path(file_path).stat().st_size
        if size > _LARGE_VIDEO_BYTES:
            return await asyncio.to_thread(
                cloudinary.uploader.upload_large,
                file_path,
                folder=folder,
                resource_type="video",
                chunk_size=_CHUNK_SIZE,
            )
        return await asyncio.to_thread(
            cloudinary.uploader.upload,
            file_path,
            folder=folder,
            resource_type="video",
        )

    async def upload_image(self, file_path: str, folder: str) -> dict:
        return await asyncio.to_thread(
            cloudinary.uploader.upload,
            file_path,
            folder=folder,
            resource_type="image",
        )

    async def delete_resource(self, public_id: str, resource_type: str = "video") -> dict:
        return await asyncio.to_thread(
            cloudinary.uploader.destroy,
            public_id,
            resource_type=resource_type,
            invalidate=True,
        )

    async def delete_by_prefix(self, prefix: str, resource_type: str = "video") -> dict:
        return await asyncio.to_thread(
            cloudinary.api.delete_resources_by_prefix,
            prefix,
            resource_type=resource_type,
            invalidate=True,
        )

    async def download_to_path(self, url: str, destination_path: str) -> str:
        async with httpx.AsyncClient(timeout=300) as client:
            async with client.stream("GET", url) as response:
                response.raise_for_status()
                async with aio_open(destination_path, "wb") as file_handle:
                    async for chunk in response.aiter_bytes():
                        await file_handle.write(chunk)
        return destination_path
