"""Track in-process video pipelines and resume jobs that died on Render restart."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path

from beanie import PydanticObjectId

logger = logging.getLogger(__name__)

_in_flight: set[str] = set()


def pipeline_claimed(project_id: str) -> bool:
    return project_id in _in_flight


def claim_pipeline(project_id: str) -> bool:
    if project_id in _in_flight:
        return False
    _in_flight.add(project_id)
    return True


def release_pipeline(project_id: str) -> None:
    _in_flight.discard(project_id)


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
                if age < 90:
                    return False
        asyncio.create_task(_resume_processing(project_id))
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
    asyncio.create_task(_kick_missing_clips(project_id))
    return True


async def _kick_missing_clips(project_id: str) -> None:
    from app.config import settings
    from app.tasks.clip_task import auto_generate_project_clips

    if not claim_pipeline(project_id):
        return
    try:
        await auto_generate_project_clips(project_id, settings.default_clip_duration_seconds)
    except Exception:
        logger.exception("Failed to start missing clip generation for %s", project_id)
    finally:
        release_pipeline(project_id)


async def _resume_processing(project_id: str) -> None:
    from app.models.project import Project
    from app.tasks.download_task import _run_download_pipeline, _set_project_error
    from app.tasks.upload_task import (
        _run_upload_pipeline,
        is_upload_project,
        restore_upload_source_from_cloudinary,
        staging_upload_path,
    )
    from app.utils.ffmpeg_utils import format_exception

    if not claim_pipeline(project_id):
        return
    try:
        project = await Project.get(PydanticObjectId(project_id))
        if not project:
            return

        if is_upload_project(project):
            await _resume_upload(project)
        else:
            await _run_download_pipeline(project_id, project.yt_url)
    except Exception as exc:
        logger.exception("Resume processing failed for %s", project_id)
        try:
            from app.models.project import Project

            fresh = await Project.get(PydanticObjectId(project_id))
            if fresh:
                await _set_project_error(fresh, format_exception(exc))
        except Exception:
            logger.exception("Could not mark resumed project %s as error", project_id)
    finally:
        release_pipeline(project_id)


async def _resume_upload(project) -> None:
    from pathlib import Path

    from app.tasks.clip_task import start_local_clip_generation
    from app.tasks.upload_task import (
        _run_upload_pipeline,
        restore_upload_source_from_cloudinary,
        staging_upload_path,
    )
    from app.config import settings

    metadata = project.metadata or {}
    original_filename = metadata.get("original_filename")
    candidates: list[Path] = []
    if original_filename:
        candidates.append(staging_upload_path(project.user_id, str(original_filename)))
    if project.local_video_path:
        candidates.append(Path(project.local_video_path))

    source = next((path for path in candidates if path.is_file()), None)
    if source:
        await _run_upload_pipeline(str(project.id), source)
        return

    if project.cloudinary_raw_url:
        await restore_upload_source_from_cloudinary(project)
        await start_local_clip_generation(str(project.id), settings.default_clip_duration_seconds)
        return

    raise FileNotFoundError(
        "Original upload is no longer on the server. Please upload the video again."
    )
