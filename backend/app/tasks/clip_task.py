import asyncio
import math
import shutil
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
from app.utils.celery_utils import celery_workers_available
from app.utils.ffmpeg_utils import get_ffmpeg_path


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


async def _acquire_raw_video(project: Project, project_id: str) -> str:
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

    asyncio.create_task(run_clip_processing(project_id, clip_id))
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
            pass

    asyncio.create_task(auto_generate_project_clips(project_id, segment_seconds))
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
    cloudinary_service = CloudinaryService()
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

        shutil.copy2(upload_path, saved_clip_path)
        shutil.copy2(thumbnail_output_path, saved_thumb_path)

        clip.local_clip_path = saved_clip_path
        clip.local_thumbnail_path = saved_thumb_path
        clip.status = ClipStatus.READY

        try:
            clip_upload = await cloudinary_service.upload_video(
                file_path=upload_path,
                folder=f"projects/{project_id}/clips/{clip_id}",
            )
            thumb_upload = await cloudinary_service.upload_image(
                file_path=thumbnail_output_path,
                folder=f"projects/{project_id}/clips/{clip_id}_thumb",
            )
            clip.cloudinary_clip_url = clip_upload.get("secure_url") or clip_upload.get("url")
            clip.cloudinary_public_id = clip_upload.get("public_id")
            clip.thumbnail_url = thumb_upload.get("secure_url") or thumb_upload.get("url")
        except Exception:
            # Keep local files — Cloudinary is optional for local development.
            pass

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

    if not project.local_video_path:
        raise RuntimeError("Project is missing a local video file")

    source_path = Path(project.local_video_path)
    if not source_path.is_file():
        raise RuntimeError("Downloaded video file is missing")

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
    use_celery = await celery_workers_available()

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
        clip_id = str(clip.id)
        # Process inline. Nesting create_clip_task.delay() from inside a Celery
        # worker (or asyncio.create_task on the worker loop) leaves clips stuck
        # in pending without files.
        await run_clip_processing(project_id, clip_id)
        queued_count += 1
        part_number += 1

    return {
        "project_id": project_id,
        "created_clips": created_count,
        "queued_clips": queued_count,
        "segment_seconds": segment_length,
        "status": "processing",
    }


@celery_app.task(name="create_clip_task")
def create_clip_task(project_id: str, clip_id: str):
    loop = cw.worker_loop if cw.worker_loop is not None else asyncio.get_event_loop()
    return loop.run_until_complete(run_clip_processing(project_id, clip_id))


@celery_app.task(name="auto_generate_clips_task")
def auto_generate_clips_task(project_id: str, clip_duration: int | None = None):
    loop = cw.worker_loop if cw.worker_loop is not None else asyncio.get_event_loop()
    return loop.run_until_complete(auto_generate_project_clips(project_id, clip_duration))
