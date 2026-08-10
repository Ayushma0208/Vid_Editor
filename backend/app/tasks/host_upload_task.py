from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from beanie import PydanticObjectId

from app.celery_worker import celery_app
import app.celery_worker as cw
from app.config import settings
from app.models.clip import Clip
from app.services.cloudinary_service import CloudinaryService
from app.services.ppd_routing import HOST_KEYS, get_host_service

def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _ensure_local_clip(clip: Clip) -> str:
    if clip.local_clip_path and Path(clip.local_clip_path).is_file():
        if clip.file_size_bytes is None:
            clip.file_size_bytes = Path(clip.local_clip_path).stat().st_size
            await clip.save()
        return clip.local_clip_path

    if not clip.cloudinary_clip_url:
        raise RuntimeError("Clip has no local file and no Cloudinary URL")

    temp_dir = Path(settings.temp_dir) / "distribute" / str(clip.id)
    temp_dir.mkdir(parents=True, exist_ok=True)
    local_path = str(temp_dir / "clip.mp4")
    await CloudinaryService().download_to_path(clip.cloudinary_clip_url, local_path)
    clip.local_clip_path = local_path
    clip.file_size_bytes = Path(local_path).stat().st_size
    await clip.save()
    return local_path


async def _set_host_state(clip_id: str, host: str, payload: dict[str, Any]) -> None:
    clip = await Clip.get(PydanticObjectId(clip_id))
    if not clip:
        return
    uploads = dict(clip.host_uploads or {})
    uploads[host] = {**uploads.get(host, {}), **payload, "updated_at": _utcnow_iso()}
    clip.host_uploads = uploads
    await clip.save()


async def _upload_one(clip_id: str, host: str, local_path: str) -> dict[str, Any]:
    service = get_host_service(host)
    if not service.is_configured():
        result = {"status": "skipped", "url": None, "error": "API key not configured"}
        await _set_host_state(clip_id, host, result)
        return {"host": host, **result}

    await _set_host_state(clip_id, host, {"status": "uploading", "url": None, "error": None})
    try:
        upload = await service.upload_file(local_path)
        result = {
            "status": "ready",
            "url": upload.get("url"),
            "file_code": upload.get("file_code"),
            "error": None,
        }
        await _set_host_state(clip_id, host, result)
        return {"host": host, **result}
    except Exception as exc:
        result = {"status": "error", "url": None, "error": str(exc)}
        await _set_host_state(clip_id, host, result)
        return {"host": host, **result}


async def _distribute_clip(clip_id: str, user_id: str, hosts: list[str]) -> dict[str, Any]:
    clip = await Clip.get(PydanticObjectId(clip_id))
    if not clip or clip.user_id != user_id:
        raise RuntimeError("Clip not found")

    selected = [h for h in hosts if h in HOST_KEYS]
    if not selected:
        raise RuntimeError("No valid hosts selected")

    local_path = await _ensure_local_clip(clip)
    results = await asyncio.gather(*[_upload_one(clip_id, host, local_path) for host in selected])
    return {"clip_id": clip_id, "results": list(results)}


@celery_app.task(bind=True, name="host_upload_task")
def host_upload_task(self, clip_id: str, user_id: str, hosts: list[str]):
    loop = cw.worker_loop if cw.worker_loop is not None else asyncio.get_event_loop()
    try:
        return loop.run_until_complete(_distribute_clip(clip_id=clip_id, user_id=user_id, hosts=hosts))
    except Exception as exc:
        async def _mark_hosts_error() -> None:
            for host in hosts:
                if host in HOST_KEYS:
                    await _set_host_state(
                        clip_id,
                        host,
                        {"status": "error", "error": str(exc)},
                    )

        loop.run_until_complete(_mark_hosts_error())
        raise exc
