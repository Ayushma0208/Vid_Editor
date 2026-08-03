from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx

from app.config import settings


class KrakenFilesError(RuntimeError):
    pass


class KrakenFilesService:
    def is_configured(self) -> bool:
        return bool(settings.krakenfiles_api_key)

    async def upload_file(self, local_path: str) -> dict[str, Any]:
        if not self.is_configured():
            raise KrakenFilesError("KrakenFiles is not configured")

        path = Path(local_path)
        if not path.is_file():
            raise KrakenFilesError(f"Local file missing: {local_path}")

        base = settings.krakenfiles_base_url.rstrip("/")
        timeout = httpx.Timeout(300.0, connect=30.0)

        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            server_resp = await client.get(f"{base}/api/server/available")
            server_resp.raise_for_status()
            server_payload = server_resp.json()
            server_url = (
                server_payload.get("url")
                or server_payload.get("server")
                or (server_payload.get("data") or {}).get("url")
            )
            if not server_url:
                raise KrakenFilesError(f"KrakenFiles server select failed: {server_payload}")

            server_url = str(server_url).rstrip("/")
            headers = {"accessToken": settings.krakenfiles_api_key}
            with path.open("rb") as file_handle:
                upload_resp = await client.post(
                    f"{server_url}/upload/server.php",
                    headers=headers,
                    files={"files[]": (path.name, file_handle, "video/mp4")},
                )
            upload_resp.raise_for_status()
            upload_payload = upload_resp.json()

        items = upload_payload if isinstance(upload_payload, list) else [upload_payload]
        if not items:
            raise KrakenFilesError("KrakenFiles returned empty upload response")

        first = items[0]
        if isinstance(first, dict) and first.get("error"):
            raise KrakenFilesError(str(first.get("error")))

        url = first.get("url") if isinstance(first, dict) else None
        file_hash = first.get("hash") if isinstance(first, dict) else None
        if not url and file_hash:
            url = f"{base}/{file_hash}"
        if not url:
            raise KrakenFilesError(f"KrakenFiles upload failed: {first}")

        return {
            "url": str(url),
            "file_code": str(file_hash) if file_hash else None,
            "raw": first,
        }
