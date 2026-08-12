from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path

from beanie import PydanticObjectId

from app.celery_worker import celery_app
import app.celery_worker as cw
from app.models.clip import Clip
from app.models.project import Project
from app.services.cloudinary_service import CloudinaryService
from app.utils.celery_utils import celery_workers_available

logger = logging.getLogger(__name__)


async def cleanup_expired_clips_for_project(project: Project) -> dict:
    project_id = str(project.id)
    clips = await Clip.find(Clip.project_id == project_id).to_list()
    deleted = 0
    cloudinary = CloudinaryService()

    for clip in clips:
        try:
            if clip.local_clip_path:
                path = Path(clip.local_clip_path)
                if path.is_file():
                    path.unlink()
            if clip.local_thumbnail_path:
                thumb = Path(clip.local_thumbnail_path)
                if thumb.is_file():
                    thumb.unlink()
            if clip.cloudinary_public_id:
                try:
                    await cloudinary.delete_resource(clip.cloudinary_public_id, resource_type="video")
                except Exception:
                    logger.exception("Failed deleting Cloudinary video %s", clip.cloudinary_public_id)
            await clip.delete()
            deleted += 1
        except Exception:
            logger.exception("Failed cleaning clip %s", clip.id)

    project.clips_expire_at = None
    project.updated_at = datetime.now(timezone.utc)
    meta = dict(project.metadata or {})
    meta["clips_cleaned_at"] = datetime.now(timezone.utc).isoformat()
    meta["clips_cleaned_count"] = deleted
    project.metadata = meta
    await project.save()
    return {"project_id": project_id, "deleted_clips": deleted}


async def cleanup_expired_clips() -> dict:
    now = datetime.now(timezone.utc)
    projects = await Project.find(
        {"clips_expire_at": {"$ne": None, "$lte": now}},
    ).to_list()
    results = []
    for project in projects:
        results.append(await cleanup_expired_clips_for_project(project))
    return {"cleaned_projects": len(results), "results": results}


async def trigger_cleanup_expired_clips() -> dict:
    if await celery_workers_available():
        try:
            task = cleanup_expired_clips_task.delay()
            return {"task_id": task.id, "execution_mode": "celery"}
        except Exception:
            pass
    asyncio.create_task(cleanup_expired_clips())
    return {"task_id": None, "execution_mode": "local-background"}


@celery_app.task(bind=True, name="cleanup_expired_clips_task")
def cleanup_expired_clips_task(self):
    loop = cw.worker_loop if cw.worker_loop is not None else asyncio.get_event_loop()
    return loop.run_until_complete(cleanup_expired_clips())
