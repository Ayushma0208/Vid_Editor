import asyncio
import logging
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

from beanie import PydanticObjectId
from fastapi import BackgroundTasks

from app.config import settings
from app.models.project import Project, ProjectStatus
from app.services.cloudinary_service import CloudinaryService
from app.services.ffmpeg_service import FfmpegService
from app.services.quality_host_routing import (
    empty_quality_asset,
    host_for_quality,
    init_quality_assets,
    nearest_target_quality,
    quality_key,
)
from app.tasks.clip_task import run_clip_processing, start_local_clip_generation
from app.tasks.download_task import _set_project_error
from app.tasks.quality_distribute_task import trigger_distribute_project_qualities
from app.utils.ffmpeg_utils import ffmpeg_available, ffmpeg_missing_message, format_exception, get_ffmpeg_path

logger = logging.getLogger(__name__)


def is_upload_project(project: Project) -> bool:
    meta = project.metadata or {}
    if meta.get("source") == "upload":
        return True
    return (project.yt_url or "").strip().lower().startswith("upload:")


def staging_upload_path(user_id: str, original_filename: str) -> Path:
    safe_name = re.sub(r"[^a-zA-Z0-9._-]+", "-", Path(original_filename).stem).strip("-") or "video"
    ext = Path(original_filename).suffix.lower() or ".mp4"
    upload_dir = Path(settings.temp_dir) / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    return upload_dir / f"{user_id}-{safe_name}{ext}"


async def _generate_thumbnail(video_path: Path, output_path: Path) -> bool:
    if not ffmpeg_available():
        return False
    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        process = await asyncio.create_subprocess_exec(
            get_ffmpeg_path() or "ffmpeg",
            "-y",
            "-ss",
            "2",
            "-i",
            str(video_path),
            "-frames:v",
            "1",
            str(output_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await process.communicate()
        return process.returncode == 0 and output_path.exists()
    except FileNotFoundError:
        return False


async def _run_upload_pipeline(project_id: str, source_path: Path) -> dict:
    if not source_path.is_file():
        raise FileNotFoundError(f"Uploaded video file not found: {source_path}")

    if not ffmpeg_available():
        raise RuntimeError(ffmpeg_missing_message())

    project = await Project.get(PydanticObjectId(project_id))
    if not project:
        raise ValueError("Project not found")

    project.status = ProjectStatus.DOWNLOADING
    project.updated_at = datetime.now(timezone.utc)
    await project.save()

    project_dir = Path(settings.temp_dir) / project_id
    project_dir.mkdir(parents=True, exist_ok=True)
    ext = source_path.suffix.lower() or ".mp4"
    dest_path = project_dir / "raw_video.mp4"

    ffmpeg_service = FfmpegService()
    if ext == ".mp4" and source_path.resolve() != dest_path.resolve():
        await asyncio.to_thread(shutil.copy2, source_path, dest_path)
    elif ext == ".mp4":
        dest_path = source_path
    else:
        await ffmpeg_service.transcode_to_mp4(str(source_path), str(dest_path))

    duration = await ffmpeg_service.probe_duration(str(dest_path))
    if not duration:
        raise RuntimeError(
            "Could not read video duration. The file may be corrupt or in an unsupported format."
        )

    thumb_path = project_dir / "thumbnail.jpg"
    thumb_ok = await _generate_thumbnail(dest_path, thumb_path)

    dims = await ffmpeg_service.probe_dimensions(str(dest_path))
    probed_height = dims[1] if dims else None
    bucket = nearest_target_quality(probed_height)
    clip_key = quality_key(settings.clip_source_quality or "720")

    qualities_dir = project_dir / "qualities"
    qualities_dir.mkdir(parents=True, exist_ok=True)
    quality_path = qualities_dir / f"{bucket}.mp4"
    if Path(dest_path).resolve() != quality_path.resolve():
        await asyncio.to_thread(shutil.copy2, dest_path, quality_path)

    assets = init_quality_assets()
    for key, asset in assets.items():
        if key == bucket:
            assets[key] = {
                **empty_quality_asset(key),
                "status": "ready",
                "local_path": str(quality_path),
                "file_size_bytes": quality_path.stat().st_size,
                "height": probed_height or int(key),
                "host": host_for_quality(key),
                "host_status": "pending",
            }
        else:
            assets[key] = {
                **empty_quality_asset(key, status="missing"),
                "host_status": "skipped",
                "host_error": "Not provided in single-file upload",
            }

    metadata = project.metadata or {}
    metadata.pop("error_message", None)
    metadata.pop("auto_clip_warning", None)
    metadata["source"] = "upload"
    metadata["upload_quality_bucket"] = bucket
    if thumb_ok:
        metadata["local_thumbnail_path"] = str(thumb_path)

    clip_height = int(clip_key) if clip_key.isdigit() else 720
    bucket_height = int(bucket) if bucket.isdigit() else 0
    # Use the uploaded file for clipping when it meets or exceeds the clip ladder height.
    # Avoid re-encoding the entire film to 720p up front (slow/fragile for long uploads).
    has_clip_source = quality_path.is_file() and bucket_height >= clip_height
    if has_clip_source:
        project.local_video_path = str(quality_path)
    elif quality_path.is_file() and bucket_height > 0:
        # Lower-than-preferred upload: still allow cutting from what we have.
        project.local_video_path = str(quality_path)
        has_clip_source = True
    else:
        project.local_video_path = str(dest_path)
        metadata["auto_clip_warning"] = (
            f"Uploaded file mapped to {bucket}p. "
            f"Clip generation requires a local video file — skipped for this upload."
        )

    project.duration_seconds = duration
    project.quality_assets = assets
    project.clip_source_quality = clip_key
    project.status = ProjectStatus.READY
    project.metadata = metadata
    project.updated_at = datetime.now(timezone.utc)
    await project.save()

    # Persist source + thumbnail to Cloudinary so Render temp clears don't kill playback.
    cloudinary = CloudinaryService()
    try:
        raw_upload = await cloudinary.upload_video(
            str(dest_path if Path(dest_path).is_file() else quality_path),
            folder=f"projects/{project_id}/raw",
        )
        project.cloudinary_raw_url = raw_upload.get("secure_url") or raw_upload.get("url")
        project.cloudinary_folder = f"projects/{project_id}/"
        await project.save()
    except Exception:
        logger.exception("Cloudinary raw upload failed for project %s", project_id)

    if thumb_ok and thumb_path.is_file():
        try:
            thumb_upload = await cloudinary.upload_image(
                str(thumb_path),
                folder=f"projects/{project_id}/thumb",
            )
            project.thumbnail_url = thumb_upload.get("secure_url") or thumb_upload.get("url")
            await project.save()
        except Exception:
            logger.exception("Cloudinary thumbnail upload failed for project %s", project_id)

    try:
        await trigger_distribute_project_qualities(project_id)
    except Exception:
        logger.exception("Quality host distribute trigger failed for project %s", project_id)

    if has_clip_source:
        try:
            await start_local_clip_generation(project_id, settings.default_clip_duration_seconds)
        except Exception as exc:
            logger.exception("Clip generation failed for project %s", project_id)
            fresh = await Project.get(PydanticObjectId(project_id))
            if fresh:
                clip_meta = fresh.metadata or {}
                clip_meta["auto_clip_warning"] = format_exception(exc)
                fresh.metadata = clip_meta
                await fresh.save()

    return {
        "project_id": project_id,
        "status": project.status.value,
        "local_video_path": project.local_video_path,
        "duration_seconds": project.duration_seconds,
        "quality_assets": project.quality_assets,
    }


async def restore_upload_source_from_cloudinary(project: Project) -> dict:
    """Re-materialize a manual-upload project from Cloudinary after temp disk wipe."""
    if not project.cloudinary_raw_url:
        raise FileNotFoundError(
            "Original upload is gone from the server and no Cloudinary backup exists. "
            "Please upload the video again."
        )

    project_id = str(project.id)
    project.status = ProjectStatus.DOWNLOADING
    metadata = dict(project.metadata or {})
    metadata.pop("error_message", None)
    metadata["source"] = "upload"
    project.metadata = metadata
    project.updated_at = datetime.now(timezone.utc)
    await project.save()

    project_dir = Path(settings.temp_dir) / project_id
    qualities_dir = project_dir / "qualities"
    project_dir.mkdir(parents=True, exist_ok=True)
    qualities_dir.mkdir(parents=True, exist_ok=True)

    dest_path = project_dir / "raw_video.mp4"
    await CloudinaryService().download_to_path(project.cloudinary_raw_url, str(dest_path))

    ffmpeg_service = FfmpegService()
    duration = await ffmpeg_service.probe_duration(str(dest_path))
    dims = await ffmpeg_service.probe_dimensions(str(dest_path))
    probed_height = dims[1] if dims else None
    bucket = nearest_target_quality(probed_height)
    clip_key = quality_key(project.clip_source_quality or settings.clip_source_quality or "720")

    quality_path = qualities_dir / f"{bucket}.mp4"
    if dest_path.resolve() != quality_path.resolve():
        await asyncio.to_thread(shutil.copy2, dest_path, quality_path)

    assets = init_quality_assets()
    for key, asset in assets.items():
        if key == bucket:
            assets[key] = {
                **empty_quality_asset(key),
                "status": "ready",
                "local_path": str(quality_path),
                "file_size_bytes": quality_path.stat().st_size,
                "height": probed_height or int(key),
                "host": host_for_quality(key),
                "host_status": "pending",
            }
        else:
            assets[key] = {
                **empty_quality_asset(key, status="missing"),
                "host_status": "skipped",
                "host_error": "Not provided in single-file upload",
            }

    project.local_video_path = str(quality_path)
    project.duration_seconds = duration or project.duration_seconds
    project.quality_assets = assets
    project.clip_source_quality = clip_key
    project.status = ProjectStatus.READY
    project.updated_at = datetime.now(timezone.utc)
    await project.save()

    from app.models.clip import Clip, ClipStatus

    clips = await Clip.find(Clip.project_id == project_id, Clip.user_id == project.user_id).to_list()
    reprocessed = 0
    for clip in clips:
        if clip.status in (ClipStatus.READY, ClipStatus.ERROR, ClipStatus.PENDING, ClipStatus.PROCESSING):
            await run_clip_processing(project_id, str(clip.id))
            reprocessed += 1

    return {
        "project_id": project_id,
        "status": project.status.value,
        "reprocessed_clips": reprocessed,
        "local_video_path": project.local_video_path,
    }


async def _run_upload_pipeline_background(project_id: str, source_path: Path) -> None:
    from app.services.pipeline_runtime import release_pipeline

    project = await Project.get(PydanticObjectId(project_id))
    if not project:
        release_pipeline(project_id)
        return
    succeeded = False
    try:
        await _run_upload_pipeline(project_id, source_path)
        succeeded = True
    except Exception as exc:
        logger.exception("Upload pipeline failed for project %s", project_id)
        fresh = await Project.get(PydanticObjectId(project_id))
        if fresh:
            await _set_project_error(fresh, format_exception(exc))
    finally:
        release_pipeline(project_id)
        uploads_root = str((Path(settings.temp_dir) / "uploads").resolve())
        if (
            succeeded
            and source_path.exists()
            and str(source_path.resolve()).startswith(uploads_root)
        ):
            try:
                source_path.unlink()
            except OSError:
                pass


async def retry_upload_processing(project: Project, background_tasks: BackgroundTasks) -> None:
    from app.services.pipeline_runtime import claim_pipeline, pipeline_claimed

    project_id = str(project.id)
    if pipeline_claimed(project_id):
        return

    metadata = dict(project.metadata or {})
    original_filename = metadata.get("original_filename")
    source_path = staging_upload_path(project.user_id, str(original_filename)) if original_filename else None
    if (source_path is None or not source_path.is_file()) and project.local_video_path:
        source_path = Path(project.local_video_path)

    if source_path is not None and source_path.is_file():
        project.status = ProjectStatus.PENDING
        metadata.pop("error_message", None)
        project.metadata = metadata
        project.updated_at = datetime.now(timezone.utc)
        await project.save()
        claim_pipeline(project_id)
        background_tasks.add_task(_run_upload_pipeline_background, project_id, source_path)
        return

    if project.cloudinary_raw_url:
        project.status = ProjectStatus.PENDING
        metadata.pop("error_message", None)
        project.metadata = metadata
        project.updated_at = datetime.now(timezone.utc)
        await project.save()
        claim_pipeline(project_id)

        async def _restore() -> None:
            from app.services.pipeline_runtime import release_pipeline

            try:
                await restore_upload_source_from_cloudinary(project)
                await start_local_clip_generation(project_id, settings.default_clip_duration_seconds)
            except Exception as exc:
                logger.exception("Cloudinary restore failed for project %s", project_id)
                fresh = await Project.get(PydanticObjectId(project_id))
                if fresh:
                    await _set_project_error(fresh, format_exception(exc))
            finally:
                release_pipeline(project_id)

        background_tasks.add_task(_restore)
        return

    raise FileNotFoundError(
        "Original upload file is no longer on the server. Please upload the video again."
    )
