from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx


class XfsUploadError(RuntimeError):
    pass


class XfsUploadService:
    """XFileSharing-style API client (Uploadrar, Up-4ever, etc.)."""

    def __init__(self, *, host_key: str, base_url: str, api_key: str):
        self.host_key = host_key
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key.strip()

    def is_configured(self) -> bool:
        return bool(self.api_key and self.base_url)

    async def upload_file(self, local_path: str) -> dict[str, Any]:
        if not self.is_configured():
            raise XfsUploadError(f"{self.host_key} is not configured")

        path = Path(local_path)
        if not path.is_file():
            raise XfsUploadError(f"Local file missing: {local_path}")

        timeout = httpx.Timeout(300.0, connect=30.0)
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            server_resp = await client.get(
                f"{self.base_url}/api/upload/server",
                params={"key": self.api_key},
            )
            server_resp.raise_for_status()
            server_payload = server_resp.json()
            if int(server_payload.get("status", 0)) != 200:
                raise XfsUploadError(
                    f"{self.host_key} server select failed: {server_payload.get('msg') or server_payload}"
                )

            upload_url = server_payload.get("result")
            sess_id = server_payload.get("sess_id")
            if not upload_url or not sess_id:
                raise XfsUploadError(f"{self.host_key} did not return upload server details")

            with path.open("rb") as file_handle:
                upload_resp = await client.post(
                    upload_url,
                    data={"sess_id": sess_id, "utype": "prem"},
                    files={"file_0": (path.name, file_handle, "video/mp4")},
                )
            upload_resp.raise_for_status()
            upload_payload = upload_resp.json()

        items = upload_payload if isinstance(upload_payload, list) else [upload_payload]
        if not items:
            raise XfsUploadError(f"{self.host_key} returned empty upload response")

        first = items[0]
        file_status = str(first.get("file_status") or "").upper()
        file_code = first.get("file_code")
        if file_status not in {"OK", "SUCCESS", ""} or not file_code:
            raise XfsUploadError(f"{self.host_key} upload failed: {first}")

        return {
            "url": f"{self.base_url}/{file_code}",
            "file_code": str(file_code),
            "raw": first,
        }
