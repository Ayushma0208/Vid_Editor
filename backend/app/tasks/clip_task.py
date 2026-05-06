import asyncio
from pathlib import Path

from beanie import PydanticObjectId

from app.celery_worker import celery_app
import app.celery_worker as cw
from app.config import settings
from app.models.clip import Clip, ClipStatus
from app.models.project import Project
from app.services.cloudinary_service import CloudinaryService
from app.services.ffmpeg_service import FfmpegService


_cache_lock = None
_raw_video_cache: dict[str, dict[str, int | str]] = {}

def get_cache_lock():
    global _cache_lock
    if _cache_lock is None:
        _cache_lock = asyncio.Lock()
    return _cache_lock

async def _acquire_raw_video(project: Project, project_id: str) -> str:
    if not project.cloudinary_raw_url:
        raise RuntimeError("Project raw video URL is missing")

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


async def _generate_thumbnail(input_path: str, output_path: str, mid_point: float) -> str:
    process = await asyncio.create_subprocess_exec(
        "ffmpeg",
        "-y",
        "-ss",
        str(mid_point),
        "-i",
        input_path,
        "-vframes",
        "1",
        "-f",
        "image2",
        output_path,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await process.communicate()
    if process.returncode != 0:
        raise RuntimeError(stderr.decode().strip() or "Thumbnail generation failed")
    return output_path


async def _process_clip(project_id: str, clip_id: str) -> dict:
    project = await Project.get(PydanticObjectId(project_id))
    clip = await Clip.get(PydanticObjectId(clip_id))
    if not project or not clip:
        raise RuntimeError("Project or clip not found")

    clip.status = ClipStatus.PROCESSING
    await clip.save()

    local_raw_path = await _acquire_raw_video(project, project_id)
    temp_dir = Path(settings.temp_dir) / project_id
    temp_dir.mkdir(parents=True, exist_ok=True)
    clip_output_path = str(temp_dir / f"{clip_id}.mp4")
    thumbnail_output_path = str(temp_dir / f"{clip_id}_thumb.jpg")

    ffmpeg_service = FfmpegService()
    cloudinary_service = CloudinaryService()

    try:
        await ffmpeg_service.cut_clip(
            input_path=local_raw_path,
            output_path=clip_output_path,
            start_time=clip.start_time,
            end_time=clip.end_time,
        )

        midpoint = clip.start_time + (clip.duration / 2)
        await _generate_thumbnail(clip_output_path, thumbnail_output_path, midpoint)
        
        clip_upload = await cloudinary_service.upload_video(
            file_path=clip_output_path,
            folder=f"projects/{project_id}/clips/{clip_id}",
        )
        thumb_upload = await cloudinary_service.upload_image(
            file_path=thumbnail_output_path,
            folder=f"projects/{project_id}/clips/{clip_id}_thumb",
        )

        clip.status = ClipStatus.READY
        clip.cloudinary_clip_url = clip_upload.get("secure_url") or clip_upload.get("url")
        clip.cloudinary_public_id = clip_upload.get("public_id")
        clip.thumbnail_url = thumb_upload.get("secure_url") or thumb_upload.get("url")
        await clip.save()
    except Exception as exc:
        clip.status = ClipStatus.ERROR
        await clip.save()
        raise exc
    finally:
        clip_file = Path(clip_output_path)
        thumb_file = Path(thumbnail_output_path)
        if clip_file.exists():
            clip_file.unlink()
        if thumb_file.exists():
            thumb_file.unlink()
        await _release_raw_video(project_id)

    return {"clip_id": clip_id, "status": clip.status.value}


@celery_app.task(name="create_clip_task")
def create_clip_task(project_id: str, clip_id: str):
    loop = cw.worker_loop if cw.worker_loop is not None else asyncio.get_event_loop()
    return loop.run_until_complete(_process_clip(project_id, clip_id))
