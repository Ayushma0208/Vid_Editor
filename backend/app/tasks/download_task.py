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
from app.services.quality_host_routing import (
    empty_quality_asset,
    host_for_quality,
    init_quality_assets,
    parse_target_qualities,
    quality_key,
)
from app.services.ytdlp_service import YTDLPService
from app.tasks.clip_task import run_clip_processing, start_local_clip_generation
from app.tasks.quality_distribute_task import trigger_distribute_project_qualities


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
    local_video_path: str | None,
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
        # Avoid dumping huge formats arrays into Mongo repeatedly.
        slim = {k: v for k, v in metadata.items() if k != "formats"}
        stored.update(slim)
        stored.pop("metadata_fetch_error", None)
        project.metadata = stored
    except Exception as exc:
        metadata = project.metadata or {}
        metadata["metadata_fetch_error"] = str(exc)
        project.metadata = metadata

    if local_video_path and not project.duration_seconds and _ffmpeg_available():
        duration = await FfmpegService().probe_duration(local_video_path)
        if duration:
            project.duration_seconds = duration


async def _download_multi_quality(project: Project, video_url: str) -> dict[str, dict]:
    ytdlp_service = YTDLPService()
    project_id = str(project.id)
    qualities_dir = Path(settings.temp_dir) / project_id / "qualities"
    qualities_dir.mkdir(parents=True, exist_ok=True)

    assets = init_quality_assets()
    project.quality_assets = assets
    project.clip_source_quality = settings.clip_source_quality or "720"
    await project.save()

    try:
        available = await ytdlp_service.list_available_heights(video_url)
    except Exception:
        available = set()

    if available:
        for height in parse_target_qualities():
            key = quality_key(height)
            asset = dict(assets.get(key) or empty_quality_asset(key))
            asset["host"] = host_for_quality(key)

            if not ytdlp_service._height_available(available, height):
                asset["status"] = "missing"
                asset["host_status"] = "skipped"
                asset["host_error"] = "Quality not available on source"
                assets[key] = asset
                project.quality_assets = assets
                await project.save()
                continue

            out_path = str(qualities_dir / f"{key}.%(ext)s")
            try:
                local_path = await ytdlp_service.download_video_quality(
                    url=video_url,
                    output_path=out_path,
                    height=height,
                )
                src = Path(local_path)
                dest = qualities_dir / f"{key}.mp4"
                if src.resolve() != dest.resolve():
                    if dest.exists():
                        dest.unlink()
                    shutil.move(str(src), str(dest))
                    local_path = str(dest)

                size = Path(local_path).stat().st_size if Path(local_path).is_file() else None
                asset.update(
                    {
                        "status": "ready",
                        "local_path": local_path,
                        "file_size_bytes": size,
                        "height": height,
                        "host": host_for_quality(key),
                        "host_status": "pending",
                        "host_url": None,
                        "host_error": None,
                    }
                )
            except Exception as exc:
                asset.update(
                    {
                        "status": "error",
                        "host_status": "skipped",
                        "host_error": str(exc),
                    }
                )
            assets[key] = asset
            project.quality_assets = assets
            await project.save()

    # Fallback: if nothing downloaded, try a single best download into the clip-source bucket.
    ready_any = any(a.get("status") == "ready" for a in assets.values())
    if not ready_any:
        clip_key = quality_key(settings.clip_source_quality or "720")
        fallback_out = str(Path(settings.temp_dir) / project_id / "raw_video.%(ext)s")
        local_path = await ytdlp_service.download_video(
            url=video_url,
            output_path=fallback_out,
            quality=f"{clip_key}p",
        )
        dest = qualities_dir / f"{clip_key}.mp4"
        src = Path(local_path)
        if src.is_file():
            if dest.exists():
                dest.unlink()
            shutil.copy2(src, dest)
            assets[clip_key] = {
                **empty_quality_asset(clip_key),
                "status": "ready",
                "local_path": str(dest),
                "file_size_bytes": dest.stat().st_size,
                "height": int(clip_key),
                "host": host_for_quality(clip_key),
                "host_status": "pending",
            }
            for key in assets:
                if key != clip_key and assets[key].get("status") != "ready":
                    assets[key]["status"] = "missing"
                    assets[key]["host_status"] = "skipped"
                    assets[key]["host_error"] = "Not downloaded (single-quality fallback)"
            project.quality_assets = assets
            await project.save()

    return assets


def _clip_source_path(assets: dict[str, dict]) -> str | None:
    clip_key = quality_key(settings.clip_source_quality or "720")
    asset = assets.get(clip_key) or {}
    path = asset.get("local_path")
    if asset.get("status") == "ready" and path and Path(str(path)).is_file():
        return str(path)
    return None


async def _run_download_pipeline(project_id: str, video_url: str) -> dict:
    project = await Project.get(PydanticObjectId(project_id))
    if not project:
        raise ValueError("Project not found")

    project.status = ProjectStatus.DOWNLOADING
    project.updated_at = datetime.now(timezone.utc)
    await project.save()

    assets = await _download_multi_quality(project, video_url)
    clip_path = _clip_source_path(assets)

    # Prefer 720 for local_video_path; else any ready quality for preview/duration.
    preview_path = clip_path
    if not preview_path:
        for key in ("1080", "720", "480", "240"):
            asset = assets.get(key) or {}
            if asset.get("status") == "ready" and asset.get("local_path"):
                preview_path = str(asset["local_path"])
                break

    project.local_video_path = clip_path  # clips require 720; may be None
    project.updated_at = datetime.now(timezone.utc)
    await project.save()

    await _enrich_project_from_download(project, video_url, preview_path or clip_path)

    metadata = project.metadata or {}
    metadata.pop("error_message", None)
    metadata.pop("auto_clip_warning", None)
    if not clip_path:
        metadata["auto_clip_warning"] = (
            f"{settings.clip_source_quality or '720'}p not available on source; "
            "clip generation skipped. Other qualities will still be hosted when ready."
        )

    # Keep a streamable path even when 720 is missing
    if not project.local_video_path and preview_path:
        project.local_video_path = preview_path

    project.status = ProjectStatus.READY
    project.quality_assets = assets
    project.metadata = metadata
    project.updated_at = datetime.now(timezone.utc)
    await project.save()

    # Full-movie host uploads for each ready quality.
    try:
        await trigger_distribute_project_qualities(project_id)
    except Exception:
        pass

    # Clips only when 720p (clip source) exists.
    if clip_path:
        project.local_video_path = clip_path
        await project.save()
        if _ffmpeg_available():
            await start_local_clip_generation(project_id, settings.default_clip_duration_seconds)
    elif preview_path:
        project.local_video_path = preview_path
        await project.save()

    return {
        "project_id": project_id,
        "status": project.status.value,
        "local_video_path": project.local_video_path,
        "quality_assets": project.quality_assets,
        "title": project.title,
        "duration_seconds": project.duration_seconds,
    }


async def _run_refetch_pipeline(project_id: str, video_url: str) -> dict:
    """Re-download source video and re-process existing clips (after temp storage was cleared)."""
    result = await _run_download_pipeline(project_id, video_url)
    project = await Project.get(PydanticObjectId(project_id))
    if not project:
        return result

    clip_path = _clip_source_path(project.quality_assets or {})
    if not clip_path:
        return {**result, "reprocessed_clips": 0}

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

    return {**result, "reprocessed_clips": reprocessed}


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
