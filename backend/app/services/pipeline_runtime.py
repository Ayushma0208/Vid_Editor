"""Track in-process video pipelines and resume jobs that died on Render restart."""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone

from beanie import PydanticObjectId

logger = logging.getLogger(__name__)

_in_flight: dict[str, float] = {}
_tasks: set[asyncio.Task] = set()
STALE_CLAIM_SECONDS = 120.0


def pipeline_claimed(project_id: str) -> bool:
    started = _in_flight.get(project_id)
    if started is None:
        return False
    if time.monotonic() - started > STALE_CLAIM_SECONDS * 5:
        _in_flight.pop(project_id, None)
        return False
    return True


def claim_pipeline(project_id: str, *, steal_after: float = STALE_CLAIM_SECONDS) -> bool:
    now = time.monotonic()
    started = _in_flight.get(project_id)
    if started is not None and now - started < steal_after:
        return False
    _in_flight[project_id] = now
    return True


def touch_pipeline(project_id: str) -> None:
    if project_id in _in_flight:
        _in_flight[project_id] = time.monotonic()


def release_pipeline(project_id: str) -> None:
    _in_flight.pop(project_id, None)


def spawn_background(coro) -> asyncio.Task:
    """Schedule a coroutine and keep a strong reference so it is not garbage-collected."""
    task = asyncio.create_task(coro)
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
    return task


async def set_processing_step(project_id: str, step: str) -> None:
    from app.models.project import Project

    touch_pipeline(project_id)
    try:
        project = await Project.get(PydanticObjectId(project_id))
        if not project:
            return
        meta = dict(project.metadata or {})
        meta["processing_step"] = step
        project.metadata = meta
        project.updated_at = datetime.now(timezone.utc)
        await project.save()
    except Exception:
        logger.exception("Could not update processing step for %s", project_id)


def _local_upload_source_exists(project) -> bool:
    from app.tasks.upload_task import find_upload_source

    return find_upload_source(project) is not None


async def fail_dead_upload_if_source_missing(project):
    """If an upload is stuck and the file is gone, mark error immediately (don't stay on Downloading)."""
    from app.models.project import Project, ProjectStatus
    from app.tasks.download_task import _set_project_error
    from app.tasks.upload_task import is_upload_project

    if not is_upload_project(project):
        return project
    if project.status not in (ProjectStatus.PENDING, ProjectStatus.DOWNLOADING):
        return project
    if pipeline_claimed(str(project.id)):
        return project
    if _local_upload_source_exists(project) or project.cloudinary_raw_url:
        return project

    await _set_project_error(
        project,
        "Original upload is no longer on the server. Please upload the video again from the dashboard.",
    )
    return await Project.get(project.id) or project


async def recover_stale_pipelines() -> None:
    from app.models.project import Project, ProjectStatus

    try:
        stuck = await Project.find(
            {"status": {"$in": [ProjectStatus.PENDING.value, ProjectStatus.DOWNLOADING.value]}}
        ).to_list()
    except Exception:
        logger.exception("Could not list stuck projects for recovery")
        return

    for project in stuck:
        await resume_stale_project(project, force=True)


async def resume_stale_project(project, force: bool = False) -> bool:
    """Restart a pending/downloading job if this process is not already running it."""
    from app.models.clip import Clip
    from app.models.project import ProjectStatus
    from app.tasks.clip_task import _resolve_clip_source_path

    project_id = str(project.id)
    status = project.status

    if status in (ProjectStatus.PENDING, ProjectStatus.DOWNLOADING):
        if pipeline_claimed(project_id):
            return False
        if not force:
            updated = project.updated_at
            if updated is not None:
                if updated.tzinfo is None:
                    updated = updated.replace(tzinfo=timezone.utc)
                age = (datetime.now(timezone.utc) - updated).total_seconds()
                if age < 20:
                    return False
        spawn_background(_resume_processing(project_id))
        return True

    if status != ProjectStatus.READY:
        return False
    if pipeline_claimed(project_id):
        return False
    if (project.metadata or {}).get("auto_clip_warning"):
        return False
    source = _resolve_clip_source_path(project)
    if not source and not project.cloudinary_raw_url:
        return False
    existing = await Clip.find(Clip.project_id == project_id).count()
    if existing > 0:
        return False
    spawn_background(_kick_missing_clips(project_id))
    return True


async def _kick_missing_clips(project_id: str) -> None:
    from app.config import settings
    from app.tasks.clip_task import auto_generate_project_clips

    if not claim_pipeline(project_id):
        return
    try:
        await set_processing_step(project_id, "Cutting 60-second clips…")
        await auto_generate_project_clips(project_id, settings.default_clip_duration_seconds)
    except Exception:
        logger.exception("Failed to start missing clip generation for %s", project_id)
    finally:
        release_pipeline(project_id)


async def _resume_processing(project_id: str) -> None:
    from app.models.project import Project
    from app.tasks.download_task import _run_download_pipeline, _set_project_error
    from app.tasks.upload_task import is_upload_project
    from app.utils.ffmpeg_utils import format_exception

    if not claim_pipeline(project_id):
        return
    try:
        project = await Project.get(PydanticObjectId(project_id))
        if not project:
            return

        await set_processing_step(project_id, "Resuming processing…")
        if is_upload_project(project):
            await _resume_upload(project)
        else:
            await _run_download_pipeline(project_id, project.yt_url)
    except Exception as exc:
        logger.exception("Resume processing failed for %s", project_id)
        try:
            fresh = await Project.get(PydanticObjectId(project_id))
            if fresh:
                await _set_project_error(fresh, format_exception(exc))
        except Exception:
            logger.exception("Could not mark resumed project %s as error", project_id)
    finally:
        release_pipeline(project_id)


async def _resume_upload(project) -> None:
    from app.config import settings
    from app.tasks.clip_task import start_local_clip_generation
    from app.tasks.upload_task import (
        _run_upload_pipeline,
        find_upload_source,
        restore_upload_source_from_cloudinary,
    )

    source = find_upload_source(project)
    if source:
        await _run_upload_pipeline(str(project.id), source)
        return

    if project.cloudinary_raw_url:
        await restore_upload_source_from_cloudinary(project)
        await start_local_clip_generation(str(project.id), settings.default_clip_duration_seconds)
        return

    raise FileNotFoundError(
        "Original upload is no longer on the server. Please upload the video again from the dashboard."
    )
