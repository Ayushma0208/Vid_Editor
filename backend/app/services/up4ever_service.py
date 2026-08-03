from __future__ import annotations

from typing import Any

from app.config import settings
from app.services.xfs_upload_service import XfsUploadService


class Up4everService:
    def __init__(self) -> None:
        self._client = XfsUploadService(
            host_key="up4ever",
            base_url=settings.up4ever_base_url,
            api_key=settings.up4ever_api_key,
        )

    def is_configured(self) -> bool:
        return self._client.is_configured()

    async def upload_file(self, local_path: str) -> dict[str, Any]:
        return await self._client.upload_file(local_path)
