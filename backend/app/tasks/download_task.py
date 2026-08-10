import asyncio
import shutil
from datetime import datetime, timezone
from pathlib import Path

from beanie import PydanticObjectId
from celery.exceptions import MaxRetriesExceededError

from app.celery_worker import celery_app
import app.celery_worker as cw
from app.config import settings
from app.models.clip import Clip, ClipStatus
from app.models.project import Project, ProjectStatus
from app.services.ffmpeg_service import FfmpegService
from app.services.ytdlp_service import YTDLPService
from app.tasks.clip_task import run_clip_processing, start_local_clip_generation
from app.tasks.summary_task import trigger_project_summary


from app.utils.ffmpeg_utils import (
    ffmpeg_available as _ffmpeg_available,
    ffmpeg_missing_message as _ffmpeg_missing_message,
    format_exception,
    is_ffmpeg_missing_error as _is_ffmpeg_missing_error,
)


async def _set_project_error(project: Project, error_message: str) -> None:
    metadata = project.metadata or {}
    metadata["error_message"] = (error_message or "").strip() or "Video processing failed."
    project.metadata = metadata
    project.status = ProjectStatus.ERROR
    project.updated_at = datetime.now(timezone.utc)
    await project.save()


async def _enrich_project_from_download(
    project: Project,
    video_url: str,
    local_video_path: str,
) -> None:
    ytdlp_service = YTDLPService()

    try:
        metadata = await ytdlp_service.get_metadata(video_url)
        if metadata.get("title"):
            project.title = str(metadata["title"])
        if metadata.get("duration"):
            project.duration_seconds = float(metadata["duration"])
        if metadata.get("thumbnail"):
            project.thumbnail_url = str(metadata["thumbnail"])
        stored = project.metadata or {}
        stored.update(metadata)
        stored.pop("metadata_fetch_error", None)
        project.metadata = stored
    except Exception as exc:
        metadata = project.metadata or {}
        metadata["metadata_fetch_error"] = str(exc)
        project.metadata = metadata

    if not project.duration_seconds and _ffmpeg_available():
        duration = await FfmpegService().probe_duration(local_video_path)
        if duration:
            project.duration_seconds = duration


async def _run_download_pipeline(project_id: str, video_url: str) -> dict:
    project = await Project.get(PydanticObjectId(project_id))
    if not project:
        raise ValueError("Project not found")

    project.status = ProjectStatus.DOWNLOADING
    project.updated_at = datetime.now(timezone.utc)
    await project.save()

    ytdlp_service = YTDLPService()
    output_template = str(Path(settings.temp_dir) / project_id / "raw_video.%(ext)s")

    local_video_path = await ytdlp_service.download_video(
        url=video_url,
        output_path=output_template,
        quality="1080p",
    )

    project.local_video_path = local_video_path
    project.updated_at = datetime.now(timezone.utc)
    await project.save()

    await _enrich_project_from_download(project, video_url, local_video_path)

    metadata = project.metadata or {}
    metadata.pop("error_message", None)
    metadata.pop("auto_clip_warning", None)

    project.status = ProjectStatus.READY
    project.local_video_path = local_video_path
    project.metadata = metadata
    project.updated_at = datetime.now(timezone.utc)
    await project.save()

    # Full-video summary for Instagram captions (runs in parallel with clipping).
    try:
        await trigger_project_summary(project_id)
    except Exception:
        pass

    if _ffmpeg_available():
        await start_local_clip_generation(project_id, settings.default_clip_duration_seconds)

    return {
        "project_id": project_id,
        "status": project.status.value,
        "local_video_path": project.local_video_path,
        "title": project.title,
        "duration_seconds": project.duration_seconds,
    }


async def _run_refetch_pipeline(project_id: str, video_url: str) -> dict:
    """Re-download source video and re-process existing clips (after temp storage was cleared)."""
    project = await Project.get(PydanticObjectId(project_id))
    if not project:
        raise ValueError("Project not found")

    project.status = ProjectStatus.DOWNLOADING
    project.updated_at = datetime.now(timezone.utc)
    await project.save()

    ytdlp_service = YTDLPService()
    output_template = str(Path(settings.temp_dir) / project_id / "raw_video.%(ext)s")

    local_video_path = await ytdlp_service.download_video(
        url=video_url,
        output_path=output_template,
        quality="1080p",
    )

    project.local_video_path = local_video_path
    project.updated_at = datetime.now(timezone.utc)
    await project.save()

    await _enrich_project_from_download(project, video_url, local_video_path)

    metadata = project.metadata or {}
    metadata.pop("error_message", None)
    metadata.pop("auto_clip_warning", None)
    project.status = ProjectStatus.READY
    project.metadata = metadata
    project.updated_at = datetime.now(timezone.utc)
    await project.save()

    clips = (
        await Clip.find(Clip.project_id == project_id, Clip.user_id == project.user_id)
        .sort("start_time")
        .to_list()
    )
    reprocessed = 0
    for clip in clips:
        if clip.status in (ClipStatus.READY, ClipStatus.ERROR, ClipStatus.PENDING, ClipStatus.PROCESSING):
            await run_clip_processing(project_id, str(clip.id))
            reprocessed += 1

    return {
        "project_id": project_id,
        "status": project.status.value,
        "local_video_path": project.local_video_path,
        "reprocessed_clips": reprocessed,
    }


@celery_app.task(bind=True, name="download_video_task", max_retries=2)
def download_video_task(self, project_id: str, video_url: str):
    try:
        if cw.worker_loop is None:
            loop = asyncio.get_event_loop()
        else:
            loop = cw.worker_loop
        return loop.run_until_complete(_run_download_pipeline(project_id, video_url))
    except Exception as exc:
        async def _mark_error() -> None:
            project = await Project.get(PydanticObjectId(project_id))
            if project:
                message = str(exc)
                if _is_ffmpeg_missing_error(exc):
                    message = _ffmpeg_missing_message()
                await _set_project_error(project, message)

        if cw.worker_loop is None:
            loop = asyncio.get_event_loop()
        else:
            loop = cw.worker_loop
        loop.run_until_complete(_mark_error())

        try:
            raise self.retry(exc=exc, countdown=30)
        except MaxRetriesExceededError:
            return {"project_id": project_id, "status": "error", "error_message": str(exc)}
