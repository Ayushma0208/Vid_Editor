import asyncio
import logging
import math
import re
import shutil
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from beanie import PydanticObjectId

from app.celery_worker import celery_app
import app.celery_worker as cw
from app.config import settings
from app.models.clip import Clip, ClipStatus, ClipType
from app.models.project import Project
from app.services.cloudinary_service import CloudinaryService
from app.services.ffmpeg_service import FfmpegService
from app.services.interest_score_service import InterestScoreService, mark_recommended_clips
from app.services.quality_host_routing import (
    TARGET_QUALITY_KEYS,
    quality_key,
)
from app.utils.celery_utils import celery_workers_available
from app.utils.ffmpeg_utils import get_ffmpeg_path

logger = logging.getLogger(__name__)


_cache_lock = None
_raw_video_cache: dict[str, dict[str, int | str]] = {}


def _format_timestamp(seconds: float) -> str:
    total = max(0, int(seconds))
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def get_cache_lock():
    global _cache_lock
    if _cache_lock is None:
        _cache_lock = asyncio.Lock()
    return _cache_lock


def _higher_ready_source(project: Project, clip_key: str) -> tuple[str, str] | None:
    """Return (quality_key, local_path) for the best ready asset taller than clip_key."""
    clip_h = int(clip_key) if clip_key.isdigit() else 720
    assets = project.quality_assets or {}
    candidates: list[tuple[int, str, str]] = []
    for key in TARGET_QUALITY_KEYS:
        if not key.isdigit() or int(key) <= clip_h:
            continue
        asset = assets.get(key) or {}
        path = _usable_local_media_path(asset.get("local_path"))
        if asset.get("status") == "ready" and path:
            candidates.append((int(key), key, path))
    if not candidates:
        return None
    candidates.sort(reverse=True)
    _, key, path = candidates[0]
    return key, path


def _usable_local_media_path(path: str | None) -> str | None:
    """Return an absolute local path only if it exists and is valid on this OS."""
    if not path:
        return None
    raw = str(path).strip()
    if not raw:
        return None
    # Windows drive paths are not usable on macOS/Linux (FFmpeg treats C: as a protocol).
    if sys.platform != "win32" and re.match(r"^[A-Za-z]:[\\/]", raw):
        return None
    candidate = Path(raw)
    if not candidate.is_file():
        return None
    # Reject accidental cwd-relative junk like backend/C:\temp\...
    if sys.platform != "win32" and re.search(r"[A-Za-z]:[\\/]", raw):
        return None
    return str(candidate.resolve())


def _resolve_clip_source_path(project: Project) -> str | None:
    """Prefer configured clip quality; otherwise any higher ready ladder file or local path."""
    clip_key = quality_key(project.clip_source_quality or settings.clip_source_quality or "720")
    assets = project.quality_assets or {}
    asset = assets.get(clip_key) or {}
    path = _usable_local_media_path(asset.get("local_path"))
    if asset.get("status") == "ready" and path:
        return path

    higher = _higher_ready_source(project, clip_key)
    if higher and _usable_local_media_path(higher[1]):
        return higher[1]

    # Same-or-lower ready assets still usable for cutting when nothing else exists.
    fallbacks: list[tuple[int, str]] = []
    for key in TARGET_QUALITY_KEYS:
        if not key.isdigit():
            continue
        item = assets.get(key) or {}
        item_path = _usable_local_media_path(item.get("local_path"))
        if item.get("status") == "ready" and item_path:
            fallbacks.append((int(key), item_path))
    if fallbacks:
        fallbacks.sort(reverse=True)
        return fallbacks[0][1]

    return _usable_local_media_path(project.local_video_path)


async def ensure_clip_source_quality(project: Project) -> str | None:
    """
    Resolve a local file suitable for cutting clips.

    Prefer the configured clip-source quality when present. If only a higher
    ready quality exists (common for single-file uploads), use that directly —
    do not re-encode the entire film first (that blocked generation for long uploads).
    """
    existing = _resolve_clip_source_path(project)
    if existing:
        meta = dict(project.metadata or {})
        if meta.pop("auto_clip_warning", None) is not None:
            project.metadata = meta
            project.local_video_path = existing
            project.updated_at = datetime.now(timezone.utc)
            await project.save()
        elif not project.local_video_path:
            project.local_video_path = existing
            project.updated_at = datetime.now(timezone.utc)
            await project.save()
        return existing

    if project.cloudinary_raw_url:
        temp_dir = Path(settings.temp_dir) / str(project.id)
        temp_dir.mkdir(parents=True, exist_ok=True)
        raw_video_path = str(temp_dir / "raw_video.mp4")
        if not Path(raw_video_path).is_file():
            await CloudinaryService().download_to_path(project.cloudinary_raw_url, raw_video_path)
        if Path(raw_video_path).is_file():
            project.local_video_path = raw_video_path
            meta = dict(project.metadata or {})
            meta.pop("auto_clip_warning", None)
            project.metadata = meta
            project.updated_at = datetime.now(timezone.utc)
            await project.save()
            return raw_video_path
    return None


async def _acquire_raw_video(project: Project, project_id: str) -> str:
    clip_source = _resolve_clip_source_path(project)
    if clip_source:
        return str(Path(clip_source).resolve())

    if project.local_video_path:
        local_path = Path(project.local_video_path)
        if local_path.is_file():
            return str(local_path.resolve())

    if not project.cloudinary_raw_url:
        raise RuntimeError("Project has no local video file and no Cloudinary raw URL")

    async with get_cache_lock():
        cached = _raw_video_cache.get(project_id)
        if cached and Path(str(cached["path"])).exists():
            cached["ref_count"] = int(cached["ref_count"]) + 1
            return str(cached["path"])

        temp_dir = Path(settings.temp_dir) / project_id
        temp_dir.mkdir(parents=True, exist_ok=True)
        raw_video_path = str(temp_dir / "raw_video.mp4")

        cloudinary_service = CloudinaryService()
        await cloudinary_service.download_to_path(project.cloudinary_raw_url, raw_video_path)

        _raw_video_cache[project_id] = {"path": raw_video_path, "ref_count": 1}
        return raw_video_path


async def _release_raw_video(project_id: str) -> None:
    async with get_cache_lock():
        cached = _raw_video_cache.get(project_id)
        if not cached:
            return
        cached["ref_count"] = int(cached["ref_count"]) - 1
        if int(cached["ref_count"]) > 0:
            return

        cached_path = Path(str(cached["path"]))
        if cached_path.exists():
            cached_path.unlink()
        _raw_video_cache.pop(project_id, None)


async def _generate_thumbnail(input_path: str, output_path: str, seek_seconds: float) -> str:
    """Generate a thumbnail from a clip file. seek_seconds is relative to that file (not the source video)."""
    safe_seek = max(0.0, seek_seconds)
    process = await asyncio.create_subprocess_exec(
        get_ffmpeg_path() or "ffmpeg",
        "-y",
        "-ss",
        str(safe_seek),
        "-i",
        input_path,
        "-frames:v",
        "1",
        "-q:v",
        "2",
        output_path,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await process.communicate()
    if process.returncode != 0:
        raise RuntimeError(stderr.decode().strip() or "Thumbnail generation failed")
    return output_path


async def _resolve_ad_clip_path(
    ffmpeg_service: FfmpegService,
    source_video_path: str,
    temp_dir: Path,
    clip_id: str,
) -> str:
    source_dimensions = await ffmpeg_service.probe_dimensions(source_video_path)
    if not source_dimensions:
        raise RuntimeError("Unable to determine source video dimensions")

    width, height = source_dimensions
    configured_ad_path = Path(settings.ad_clip_path).expanduser() if settings.ad_clip_path else None
    if configured_ad_path and configured_ad_path.is_file():
        normalized_ad_path = temp_dir / f"{clip_id}_ad.mp4"
        await ffmpeg_service.resize_video(str(configured_ad_path), str(normalized_ad_path), width, height)
        return str(normalized_ad_path)

    default_ad_path = temp_dir / f"{clip_id}_default_ad.mp4"
    await ffmpeg_service.create_default_ad_clip(
        str(default_ad_path),
        width,
        height,
        settings.default_ad_duration_seconds,
    )
    return str(default_ad_path)


async def enqueue_clip_processing(project_id: str, clip_id: str) -> str:
    if await celery_workers_available():
        try:
            task = create_clip_task.delay(project_id, clip_id)
            return task.id
        except Exception:
            pass

    async def _local() -> None:
        await run_clip_processing(project_id, clip_id)
        clip = await Clip.get(PydanticObjectId(clip_id))
        if clip:
            await mark_recommended_clips(project_id, clip.user_id)

    asyncio.create_task(_local())
    return "local-background"


async def trigger_auto_generate_clips(project_id: str, clip_duration: int | None = None) -> dict[str, Any]:
    segment_seconds = clip_duration or settings.default_clip_duration_seconds

    if await celery_workers_available():
        try:
            task = auto_generate_clips_task.delay(project_id, segment_seconds)
            return {
                "task_id": task.id,
                "execution_mode": "celery",
                "segment_seconds": segment_seconds,
            }
        except Exception:
            logger.exception("Failed to enqueue Celery clip generation for %s", project_id)

    async def _local() -> None:
        try:
            result = await auto_generate_project_clips(project_id, segment_seconds)
            logger.info("Local clip generation finished for %s: %s", project_id, result)
        except Exception:
            logger.exception("Local clip generation failed for project %s", project_id)
            try:
                project = await Project.get(PydanticObjectId(project_id))
                if project:
                    meta = dict(project.metadata or {})
                    meta["auto_clip_warning"] = "Clip generation failed unexpectedly. Check server logs."
                    project.metadata = meta
                    project.updated_at = datetime.now(timezone.utc)
                    await project.save()
            except Exception:
                logger.exception("Could not persist clip generation failure for %s", project_id)

    asyncio.create_task(_local())
    return {"task_id": None, "execution_mode": "local-background", "segment_seconds": segment_seconds}


async def start_local_clip_generation(project_id: str, clip_duration: int | None = None) -> None:
    """Generate clips locally without Celery/Redis."""
    segment_seconds = clip_duration or settings.default_clip_duration_seconds
    if await celery_workers_available():
        await trigger_auto_generate_clips(project_id, segment_seconds)
        return
    await auto_generate_project_clips(project_id, segment_seconds)


def _should_append_ad() -> bool:
    configured = (settings.ad_clip_path or "").strip()
    return bool(configured and Path(configured).expanduser().is_file())


async def run_clip_processing(project_id: str, clip_id: str) -> dict:
    project = await Project.get(PydanticObjectId(project_id))
    clip = await Clip.get(PydanticObjectId(clip_id))
    if not project or not clip:
        raise RuntimeError("Project or clip not found")

    clip.status = ClipStatus.PROCESSING
    await clip.save()

    local_raw_path = await _acquire_raw_video(project, project_id)
    temp_dir = Path(settings.temp_dir) / project_id
    clips_dir = temp_dir / "clips"
    temp_dir.mkdir(parents=True, exist_ok=True)
    clips_dir.mkdir(parents=True, exist_ok=True)

    clip_output_path = str(temp_dir / f"{clip_id}_work.mp4")
    final_clip_path = str(temp_dir / f"{clip_id}_final.mp4")
    thumbnail_output_path = str(temp_dir / f"{clip_id}_thumb_work.jpg")
    saved_clip_path = str(clips_dir / f"{clip_id}.mp4")
    saved_thumb_path = str(clips_dir / f"{clip_id}_thumb.jpg")

    ffmpeg_service = FfmpegService()
    append_ad = _should_append_ad()

    try:
        await ffmpeg_service.cut_clip(
            input_path=local_raw_path,
            output_path=clip_output_path,
            start_time=clip.start_time,
            end_time=clip.end_time,
            part_label=clip.label or None,
        )

        await _generate_thumbnail(clip_output_path, thumbnail_output_path, clip.duration / 2)

        upload_path = clip_output_path
        if append_ad:
            ad_clip_path = await _resolve_ad_clip_path(ffmpeg_service, clip_output_path, temp_dir, clip_id)
            await ffmpeg_service.concat_videos(clip_output_path, ad_clip_path, final_clip_path)
            upload_path = final_clip_path

        await asyncio.to_thread(shutil.copy2, upload_path, saved_clip_path)
        await asyncio.to_thread(shutil.copy2, thumbnail_output_path, saved_thumb_path)

        clip.local_clip_path = saved_clip_path
        clip.local_thumbnail_path = saved_thumb_path
        clip.file_size_bytes = Path(saved_clip_path).stat().st_size
        clip.status = ClipStatus.READY

        # Score the content cut (without optional ad) so ads don't inflate interest.
        try:
            await InterestScoreService(ffmpeg_service).apply_scores_to_clip(clip, clip_output_path)
        except Exception:
            clip.interest_score = None
            clip.interest_audio = None
            clip.interest_motion = None

        try:
            await _upload_clip_to_cloudinary(
                clip,
                video_path=saved_clip_path,
                thumb_path=saved_thumb_path,
            )
        except Exception:
            logger.exception(
                "Cloudinary clip upload failed project=%s clip=%s — Instagram publish needs a retry",
                project_id,
                clip_id,
            )

        await clip.save()
    except Exception as exc:
        clip.status = ClipStatus.ERROR
        await clip.save()
        raise exc
    finally:
        for path in (clip_output_path, final_clip_path, thumbnail_output_path):
            file_path = Path(path)
            if file_path.exists():
                file_path.unlink()
        if append_ad:
            ad_file = Path(temp_dir / f"{clip_id}_ad.mp4")
            if ad_file.exists():
                ad_file.unlink()
        await _release_raw_video(project_id)

    return {"clip_id": clip_id, "status": clip.status.value}


async def auto_generate_project_clips(project_id: str, clip_duration: int | None = None) -> dict[str, int | str]:
    project = await Project.get(PydanticObjectId(project_id))
    if not project:
        raise RuntimeError("Project not found")

    clip_key = quality_key(project.clip_source_quality or settings.clip_source_quality or "720")
    try:
        clip_source = await ensure_clip_source_quality(project)
    except Exception as exc:
        meta = dict(project.metadata or {})
        meta["auto_clip_warning"] = f"Failed to prepare {clip_key}p clip source: {exc}"
        project.metadata = meta
        project.updated_at = datetime.now(timezone.utc)
        await project.save()
        return {
            "project_id": project_id,
            "created_clips": 0,
            "queued_clips": 0,
            "segment_seconds": clip_duration or settings.default_clip_duration_seconds,
            "recommended_clips": 0,
            "status": "skipped",
            "warning": meta["auto_clip_warning"],
        }
    if not clip_source:
        project = await Project.get(PydanticObjectId(project_id)) or project
        clip_source = _resolve_clip_source_path(project)
    if not clip_source:
        meta = dict(project.metadata or {})
        meta["auto_clip_warning"] = (
            f"{clip_key}p source is required for clip generation but was not found. Skipping clips."
        )
        project.metadata = meta
        project.updated_at = datetime.now(timezone.utc)
        await project.save()
        return {
            "project_id": project_id,
            "created_clips": 0,
            "queued_clips": 0,
            "segment_seconds": clip_duration or settings.default_clip_duration_seconds,
            "recommended_clips": 0,
            "status": "skipped",
            "warning": meta["auto_clip_warning"],
        }

    # Ensure downstream processing uses the clip-source path.
    project.local_video_path = clip_source
    await project.save()

    source_path = Path(clip_source)
    segment_length = max(int(clip_duration or settings.default_clip_duration_seconds), 1)
    ffmpeg_service = FfmpegService()
    duration_seconds = project.duration_seconds or await ffmpeg_service.probe_duration(str(source_path))
    if not duration_seconds:
        raise RuntimeError("Unable to determine source video duration")

    existing_clips = await Clip.find(Clip.project_id == project_id, Clip.user_id == project.user_id).to_list()
    for existing_clip in existing_clips:
        await existing_clip.delete()

    created_count = 0
    queued_count = 0
    part_number = 1
    segment_starts = range(0, int(math.ceil(duration_seconds)), segment_length)
    created_ids: list[str] = []

    for start_time in segment_starts:
        end_time = min(float(start_time + segment_length), float(duration_seconds))
        if end_time - start_time < 1:
            continue

        clip = Clip(
            project_id=project_id,
            user_id=project.user_id,
            label=f"Part-{part_number}",
            start_time=float(start_time),
            end_time=end_time,
            duration=end_time - float(start_time),
            clip_type=(
                ClipType.THIRTY_SECONDS
                if segment_length == 30
                else ClipType.SIXTY_SECONDS
                if segment_length == 60
                else ClipType.CUSTOM
            ),
            status=ClipStatus.PENDING,
            created_at=project.created_at,
        )
        await clip.insert()
        created_count += 1
        created_ids.append(str(clip.id))
        part_number += 1

    # Process after all rows exist so the UI can show pending clips immediately.
    from app.services.pipeline_runtime import set_processing_step

    total = len(created_ids)
    for index, clip_id in enumerate(created_ids, start=1):
        await set_processing_step(project_id, f"Cutting clip {index} of {total}…")
        await run_clip_processing(project_id, clip_id)
        queued_count += 1

    rank = await mark_recommended_clips(project_id, project.user_id)

    ttl_days = max(1, int(settings.clip_ttl_days or 7))
    project.clips_expire_at = datetime.now(timezone.utc) + timedelta(days=ttl_days)
    project.updated_at = datetime.now(timezone.utc)
    await project.save()

    return {
        "project_id": project_id,
        "created_clips": created_count,
        "queued_clips": queued_count,
        "segment_seconds": segment_length,
        "recommended_clips": rank.get("recommended", 0),
        "clips_expire_at": project.clips_expire_at.isoformat() if project.clips_expire_at else None,
        "status": "processing",
    }


CLOUDINARY_SYNC_KEY = "cloudinary_clip_sync"


def _cloudinary_configured() -> bool:
    return CloudinaryService().is_configured()


async def _set_cloudinary_sync_meta(project_id: str, patch: dict[str, Any]) -> None:
    project = await Project.get(PydanticObjectId(project_id))
    if not project:
        return
    meta = dict(project.metadata or {})
    current = dict(meta.get(CLOUDINARY_SYNC_KEY) or {})
    current.update(patch)
    current["updated_at"] = datetime.now(timezone.utc).isoformat()
    meta[CLOUDINARY_SYNC_KEY] = current
    project.metadata = meta
    project.updated_at = datetime.now(timezone.utc)
    await project.save()


async def _upload_clip_to_cloudinary(
    clip: Clip,
    video_path: str,
    thumb_path: str | None = None,
) -> Clip:
    if not _cloudinary_configured():
        raise RuntimeError("Cloudinary is not configured")
    if not Path(video_path).is_file():
        raise FileNotFoundError(f"Clip file not found: {video_path}")

    service = CloudinaryService()
    last_error: Exception | None = None
    clip_id = str(clip.id)
    for attempt in range(1, 4):
        try:
            clip_upload = await service.upload_video(
                file_path=video_path,
                folder=f"projects/{clip.project_id}/clips/{clip_id}",
            )
            url = clip_upload.get("secure_url") or clip_upload.get("url")
            if not url:
                raise RuntimeError("Cloudinary did not return a video URL")
            clip.cloudinary_clip_url = url
            clip.cloudinary_public_id = clip_upload.get("public_id")
            if thumb_path and Path(thumb_path).is_file():
                try:
                    thumb_upload = await service.upload_image(
                        file_path=thumb_path,
                        folder=f"projects/{clip.project_id}/clips/{clip_id}_thumb",
                    )
                    clip.thumbnail_url = thumb_upload.get("secure_url") or thumb_upload.get("url")
                except Exception:
                    logger.exception("Cloudinary thumbnail upload failed clip=%s", clip_id)
            await clip.save()
            return clip
        except Exception as exc:
            last_error = exc
            logger.exception("Cloudinary clip upload attempt %s failed clip=%s", attempt, clip_id)
            if attempt < 3:
                await asyncio.sleep(2 * attempt)
    raise RuntimeError(f"Cloudinary clip upload failed after retries: {last_error}") from last_error


async def ensure_clip_on_cloudinary(project_id: str, clip_id: str) -> Clip:
    clip = await Clip.get(PydanticObjectId(clip_id))
    if not clip or clip.project_id != project_id:
        raise RuntimeError("Clip not found")
    if clip.cloudinary_clip_url:
        return clip

    local_path = Path(clip.local_clip_path) if clip.local_clip_path else None
    if local_path and local_path.is_file():
        return await _upload_clip_to_cloudinary(
            clip,
            video_path=str(local_path),
            thumb_path=clip.local_thumbnail_path,
        )

    await run_clip_processing(project_id, clip_id)
    refreshed = await Clip.get(PydanticObjectId(clip_id))
    if not refreshed or not refreshed.cloudinary_clip_url:
        raise RuntimeError("Clip was rebuilt but Cloudinary upload still failed")
    return refreshed


async def upload_missing_project_clips_to_cloudinary(project_id: str) -> dict[str, Any]:
    project = await Project.get(PydanticObjectId(project_id))
    if not project:
        raise RuntimeError("Project not found")
    if not _cloudinary_configured():
        raise RuntimeError("Cloudinary is not configured")

    clips = await Clip.find(Clip.project_id == project_id, Clip.user_id == project.user_id).sort("+start_time").to_list()
    missing = [c for c in clips if not c.cloudinary_clip_url]
    await _set_cloudinary_sync_meta(
        project_id,
        {
            "status": "running",
            "total": len(clips),
            "missing": len(missing),
            "uploaded": 0,
            "failed": 0,
            "error": None,
        },
    )

    uploaded = 0
    failed = 0
    last_error = None
    from app.services.pipeline_runtime import set_processing_step

    for index, clip in enumerate(missing, start=1):
        await set_processing_step(project_id, f"Uploading clip {index} of {len(missing)} to Cloudinary…")
        try:
            await ensure_clip_on_cloudinary(project_id, str(clip.id))
            uploaded += 1
        except Exception as exc:
            failed += 1
            last_error = str(exc)
            logger.exception("Failed uploading clip %s to Cloudinary", clip.id)
        await _set_cloudinary_sync_meta(
            project_id,
            {
                "status": "running",
                "uploaded": uploaded,
                "failed": failed,
                "missing": max(0, len(missing) - uploaded - failed),
            },
        )

    status_value = "done" if failed == 0 else "error"
    await _set_cloudinary_sync_meta(
        project_id,
        {
            "status": status_value,
            "uploaded": uploaded,
            "failed": failed,
            "missing": failed,
            "error": last_error if failed else None,
        },
    )
    try:
        await set_processing_step(project_id, "Cloudinary clip upload complete.")
    except Exception:
        pass
    return {
        "project_id": project_id,
        "total": len(clips),
        "uploaded": uploaded,
        "failed": failed,
        "status": status_value,
    }


async def trigger_upload_project_clips_to_cloudinary(project_id: str) -> dict[str, Any]:
    if await celery_workers_available():
        try:
            task = upload_project_clips_to_cloudinary_task.delay(project_id)
            return {"task_id": task.id, "execution_mode": "celery"}
        except Exception:
            logger.exception("Failed to enqueue Cloudinary clip upload for %s", project_id)
    asyncio.create_task(upload_missing_project_clips_to_cloudinary(project_id))
    return {"task_id": None, "execution_mode": "local-background"}


@celery_app.task(name="create_clip_task")
def create_clip_task(project_id: str, clip_id: str):
    loop = cw.worker_loop if cw.worker_loop is not None else asyncio.get_event_loop()

    async def _run() -> dict:
        result = await run_clip_processing(project_id, clip_id)
        clip = await Clip.get(PydanticObjectId(clip_id))
        if clip:
            await mark_recommended_clips(project_id, clip.user_id)
        return result

    return loop.run_until_complete(_run())


@celery_app.task(name="auto_generate_clips_task")
def auto_generate_clips_task(project_id: str, clip_duration: int | None = None):
    loop = cw.worker_loop if cw.worker_loop is not None else asyncio.get_event_loop()
    return loop.run_until_complete(auto_generate_project_clips(project_id, clip_duration))


@celery_app.task(name="upload_project_clips_to_cloudinary_task")
def upload_project_clips_to_cloudinary_task(project_id: str):
    loop = cw.worker_loop if cw.worker_loop is not None else asyncio.get_event_loop()
    return loop.run_until_complete(upload_missing_project_clips_to_cloudinary(project_id))
