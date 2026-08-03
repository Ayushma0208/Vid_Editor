from __future__ import annotations

from typing import Any

from app.config import settings
from app.services.xfs_upload_service import XfsUploadService


class UploadrarService:
    def __init__(self) -> None:
        self._client = XfsUploadService(
            host_key="uploadrar",
            base_url=settings.uploadrar_base_url,
            api_key=settings.uploadrar_api_key,
        )

    def is_configured(self) -> bool:
        return self._client.is_configured()

    async def upload_file(self, local_path: str) -> dict[str, Any]:
        return await self._client.upload_file(local_path)
