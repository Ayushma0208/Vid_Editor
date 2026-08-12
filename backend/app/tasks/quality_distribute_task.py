from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from beanie import PydanticObjectId

from app.celery_worker import celery_app
import app.celery_worker as cw
from app.models.project import Project
from app.services.ppd_routing import get_host_service
from app.services.quality_host_routing import (
    TARGET_QUALITY_KEYS,
    empty_quality_asset,
    host_for_quality,
)
from app.utils.celery_utils import celery_workers_available

logger = logging.getLogger(__name__)


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _save_quality_asset(project_id: str, quality: str, patch: dict[str, Any]) -> None:
    project = await Project.get(PydanticObjectId(project_id))
    if not project:
        return
    assets = dict(project.quality_assets or {})
    current = dict(assets.get(quality) or empty_quality_asset(quality))
    current.update(patch)
    current["updated_at"] = _utcnow_iso()
    assets[quality] = current
    project.quality_assets = assets
    project.updated_at = datetime.now(timezone.utc)
    await project.save()


async def _upload_one_quality(project_id: str, quality: str, asset: dict[str, Any]) -> dict[str, Any]:
    local_path = asset.get("local_path")
    host = asset.get("host") or host_for_quality(quality)

    if asset.get("status") != "ready" or not local_path or not Path(str(local_path)).is_file():
        result = {
            "host_status": "skipped",
            "host": host,
            "host_url": None,
            "host_error": "Quality file not ready",
        }
        await _save_quality_asset(project_id, quality, result)
        return {"quality": quality, **result}

    if not host:
        result = {
            "host_status": "skipped",
            "host": None,
            "host_url": None,
            "host_error": "No host mapped for quality",
        }
        await _save_quality_asset(project_id, quality, result)
        return {"quality": quality, **result}

    service = get_host_service(host)
    if not service.is_configured():
        result = {
            "host_status": "skipped",
            "host": host,
            "host_url": None,
            "host_error": "API key not configured",
        }
        await _save_quality_asset(project_id, quality, result)
        return {"quality": quality, **result}

    await _save_quality_asset(
        project_id,
        quality,
        {"host": host, "host_status": "uploading", "host_url": None, "host_error": None},
    )
    try:
        upload = await service.upload_file(str(local_path))
        result = {
            "host": host,
            "host_status": "ready",
            "host_url": upload.get("url"),
            "file_code": upload.get("file_code"),
            "host_error": None,
        }
        await _save_quality_asset(project_id, quality, result)
        return {"quality": quality, **result}
    except Exception as exc:
        logger.exception("Quality host upload failed project=%s quality=%s", project_id, quality)
        result = {
            "host": host,
            "host_status": "error",
            "host_url": None,
            "host_error": str(exc),
        }
        await _save_quality_asset(project_id, quality, result)
        return {"quality": quality, **result}


async def distribute_project_qualities(
    project_id: str,
    *,
    qualities: list[str] | None = None,
    only_failed: bool = False,
) -> dict[str, Any]:
    project = await Project.get(PydanticObjectId(project_id))
    if not project:
        raise RuntimeError("Project not found")

    assets = dict(project.quality_assets or {})
    selected = [q for q in (qualities or list(TARGET_QUALITY_KEYS)) if q in TARGET_QUALITY_KEYS]
    to_upload: list[tuple[str, dict[str, Any]]] = []
    for key in selected:
        asset = dict(assets.get(key) or empty_quality_asset(key, status="missing"))
        if asset.get("status") != "ready":
            continue
        host_status = (asset.get("host_status") or "").lower()
        if only_failed:
            # Retry errors / skipped / never-started; skip already-ready uploads.
            if host_status == "ready" and asset.get("host_url"):
                continue
            if host_status not in ("error", "skipped", "pending", "uploading", ""):
                continue
        else:
            # First pass: skip qualities already hosted successfully.
            if host_status == "ready" and asset.get("host_url"):
                continue
        to_upload.append((key, asset))

    results = await asyncio.gather(*[_upload_one_quality(project_id, q, a) for q, a in to_upload])
    return {
        "project_id": project_id,
        "uploaded": len(results),
        "results": list(results),
    }


async def trigger_distribute_project_qualities(
    project_id: str,
    *,
    qualities: list[str] | None = None,
    only_failed: bool = False,
) -> dict[str, Any]:
    if await celery_workers_available():
        try:
            task = distribute_project_qualities_task.delay(project_id, qualities, only_failed)
            return {"task_id": task.id, "execution_mode": "celery"}
        except Exception:
            pass
    asyncio.create_task(
        distribute_project_qualities(project_id, qualities=qualities, only_failed=only_failed)
    )
    return {"task_id": None, "execution_mode": "local-background"}


@celery_app.task(bind=True, name="distribute_project_qualities_task")
def distribute_project_qualities_task(
    self,
    project_id: str,
    qualities: list[str] | None = None,
    only_failed: bool = False,
):
    loop = cw.worker_loop if cw.worker_loop is not None else asyncio.get_event_loop()
    return loop.run_until_complete(
        distribute_project_qualities(project_id, qualities=qualities, only_failed=only_failed)
    )
