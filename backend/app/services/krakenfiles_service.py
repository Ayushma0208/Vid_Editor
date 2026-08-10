from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx

from app.config import settings


class KrakenFilesError(RuntimeError):
    pass


def _unwrap_payload(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise KrakenFilesError(f"KrakenFiles returned unexpected payload: {payload}")

    status = payload.get("status")
    if status not in (None, 200):
        data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
        message = data.get("message") or payload.get("msg") or payload
        raise KrakenFilesError(f"KrakenFiles API error ({status}): {message}")

    data = payload.get("data")
    if isinstance(data, dict):
        return data
    return payload


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
        headers = {"Accept": "application/json", "X-AUTH-TOKEN": settings.krakenfiles_api_key}

        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            server_resp = await client.get(f"{base}/api/server/available", headers=headers)
            server_resp.raise_for_status()
            server_data = _unwrap_payload(server_resp.json())

            upload_url = server_data.get("url")
            server_access_token = server_data.get("serverAccessToken")
            if not upload_url or not server_access_token:
                raise KrakenFilesError(f"KrakenFiles server select failed: {server_data}")

            with path.open("rb") as file_handle:
                upload_resp = await client.post(
                    str(upload_url),
                    headers=headers,
                    data={"serverAccessToken": server_access_token},
                    files={"file": (path.name, file_handle, "video/mp4")},
                )
            upload_resp.raise_for_status()
            upload_data = _unwrap_payload(upload_resp.json())

        if upload_data.get("error"):
            raise KrakenFilesError(str(upload_data.get("error")))

        url = upload_data.get("url")
        file_hash = upload_data.get("hash")
        if not url and file_hash:
            url = f"{base}/view/{file_hash}/file.html"
        if not url:
            raise KrakenFilesError(f"KrakenFiles upload failed: {upload_data}")

        return {
            "url": str(url),
            "file_code": str(file_hash) if file_hash else None,
            "raw": upload_data,
        }
