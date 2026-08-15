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
    TARGET_QUALITY_KEYS,
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


async def _copy_or_transcode_mp4(ffmpeg_service: FfmpegService, source: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    ext = source.suffix.lower() or ".mp4"
    if ext == ".mp4":
        if source.resolve() != dest.resolve():
            await asyncio.to_thread(shutil.copy2, source, dest)
        return
    await ffmpeg_service.transcode_to_mp4(str(source), str(dest))


async def _ingest_quality_uploads(
    ffmpeg_service: FfmpegService,
    project_dir: Path,
    source_paths: list[Path],
) -> tuple[dict, Path, float | None, str]:
    """Probe each file, bucket by height (240/480/720/1080), write quality copies."""
    qualities_dir = project_dir / "qualities"
    ingest_dir = project_dir / "ingest"
    qualities_dir.mkdir(parents=True, exist_ok=True)
    ingest_dir.mkdir(parents=True, exist_ok=True)

    chosen: dict[str, dict] = {}
    duration: float | None = None
    best_raw: Path | None = None
    best_raw_height = -1

    for index, source in enumerate(source_paths):
        if not source.is_file():
            continue
        temp_mp4 = ingest_dir / f"file-{index}.mp4"
        await _copy_or_transcode_mp4(ffmpeg_service, source, temp_mp4)
        probed_duration = await ffmpeg_service.probe_duration(str(temp_mp4))
        if probed_duration and (duration is None or probed_duration > duration):
            duration = probed_duration
        dims = await ffmpeg_service.probe_dimensions(str(temp_mp4))
        height = dims[1] if dims else None
        bucket = nearest_target_quality(height)
        target_height = int(bucket) if bucket.isdigit() else 0
        distance = abs((height or target_height) - target_height)
        previous = chosen.get(bucket)
        if previous is None or distance < int(previous["distance"]):
            dest = qualities_dir / f"{bucket}.mp4"
            await _copy_or_transcode_mp4(ffmpeg_service, temp_mp4, dest)
            chosen[bucket] = {
                "path": dest,
                "height": height or target_height,
                "distance": distance,
                "size": dest.stat().st_size,
            }
        if (height or 0) > best_raw_height:
            best_raw_height = height or 0
            best_raw = temp_mp4

    dest_path = project_dir / "raw_video.mp4"
    if best_raw is not None and best_raw.resolve() != dest_path.resolve():
        await asyncio.to_thread(shutil.copy2, best_raw, dest_path)
    elif best_raw is None:
        for source in source_paths:
            if source.is_file():
                await _copy_or_transcode_mp4(ffmpeg_service, source, dest_path)
                break

    assets = init_quality_assets()
    for key in list(assets):
        if key in chosen:
            info = chosen[key]
            assets[key] = {
                **empty_quality_asset(key),
                "status": "ready",
                "local_path": str(info["path"]),
                "file_size_bytes": info["size"],
                "height": info["height"],
                "host": host_for_quality(key),
                "host_status": "pending",
            }
        else:
            assets[key] = {
                **empty_quality_asset(key, status="missing"),
                "host_status": "skipped",
                "host_error": "Not included in this upload",
            }

    primary_bucket = nearest_target_quality(best_raw_height if best_raw_height > 0 else None)
    shutil.rmtree(ingest_dir, ignore_errors=True)
    return assets, dest_path, duration, primary_bucket


async def _run_upload_pipeline(
    project_id: str,
    source_path: Path,
    extra_paths: list[Path] | None = None,
) -> dict:
    source_paths = [path for path in [source_path, *(extra_paths or [])] if path.is_file()]
    if not source_paths:
        raise FileNotFoundError(f"Uploaded video file not found: {source_path}")

    if not ffmpeg_available():
        raise RuntimeError(ffmpeg_missing_message())

    project = await Project.get(PydanticObjectId(project_id))
    if not project:
        raise ValueError("Project not found")

    project.status = ProjectStatus.DOWNLOADING
    project.updated_at = datetime.now(timezone.utc)
    await project.save()
    from app.services.pipeline_runtime import set_processing_step

    await set_processing_step(project_id, "Preparing uploaded video…")

    project_dir = Path(settings.temp_dir) / project_id
    project_dir.mkdir(parents=True, exist_ok=True)
    ffmpeg_service = FfmpegService()

    await set_processing_step(project_id, "Detecting quality and sorting files…")
    assets, dest_path, duration, bucket = await _ingest_quality_uploads(
        ffmpeg_service, project_dir, source_paths
    )
    if not duration:
        duration = await ffmpeg_service.probe_duration(str(dest_path))
    if not duration:
        raise RuntimeError(
            "Could not read video duration. The file may be corrupt or in an unsupported format."
        )

    thumb_path = project_dir / "thumbnail.jpg"
    thumb_ok = await _generate_thumbnail(dest_path, thumb_path)
    clip_key = quality_key(settings.clip_source_quality or "720")

    metadata = project.metadata or {}
    metadata.pop("error_message", None)
    metadata.pop("auto_clip_warning", None)
    metadata["source"] = "upload"
    metadata["upload_quality_bucket"] = bucket
    metadata["upload_quality_buckets"] = [
        key for key, asset in assets.items() if asset.get("status") == "ready"
    ]
    if thumb_ok:
        metadata["local_thumbnail_path"] = str(thumb_path)

    ready_keys = [
        key
        for key, asset in assets.items()
        if asset.get("status") == "ready" and asset.get("local_path")
    ]
    clip_source_key = clip_key if clip_key in ready_keys else None
    if clip_source_key is None and ready_keys:
        clip_source_key = max(ready_keys, key=lambda key: int(key) if key.isdigit() else 0)
    clip_path = Path(assets[clip_source_key]["local_path"]) if clip_source_key else dest_path
    has_clip_source = clip_path.is_file()
    if has_clip_source:
        project.local_video_path = str(clip_path)
    else:
        project.local_video_path = str(dest_path)
        metadata["auto_clip_warning"] = (
            f"Uploaded files mapped to {', '.join(ready_keys) or bucket}p. "
            "Clip generation requires a local video file — skipped for this upload."
        )

    project.duration_seconds = duration
    project.quality_assets = assets
    project.clip_source_quality = clip_key
    project.status = ProjectStatus.READY
    project.metadata = metadata
    project.updated_at = datetime.now(timezone.utc)
    await project.save()

    await set_processing_step(project_id, "Saving a backup of the video…")
    # Persist source + thumbnail to Cloudinary so Render temp clears don't kill playback.
    cloudinary = CloudinaryService()
    try:
        raw_upload = await cloudinary.upload_video(
            str(dest_path if Path(dest_path).is_file() else project.local_video_path),
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
            await set_processing_step(project_id, "Cutting 60-second clips…")
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


async def attach_quality_file(project_id: str, quality: str, source_path: Path) -> dict:
    """Attach a separately encoded quality file (240/480/720/1080) to an existing project."""
    key = quality_key(quality)
    if key not in TARGET_QUALITY_KEYS:
        raise ValueError(f"Unsupported quality. Use one of: {', '.join(TARGET_QUALITY_KEYS)}")

    if not source_path.is_file():
        raise FileNotFoundError(f"Uploaded video file not found: {source_path}")

    if not ffmpeg_available():
        raise RuntimeError(ffmpeg_missing_message())

    project = await Project.get(PydanticObjectId(project_id))
    if not project:
        raise ValueError("Project not found")

    project_dir = Path(settings.temp_dir) / project_id
    qualities_dir = project_dir / "qualities"
    qualities_dir.mkdir(parents=True, exist_ok=True)
    dest_path = qualities_dir / f"{key}.mp4"

    ffmpeg_service = FfmpegService()
    ext = source_path.suffix.lower() or ".mp4"
    if ext == ".mp4":
        if source_path.resolve() != dest_path.resolve():
            await asyncio.to_thread(shutil.copy2, source_path, dest_path)
    else:
        await ffmpeg_service.transcode_to_mp4(str(source_path), str(dest_path))

    dims = await ffmpeg_service.probe_dimensions(str(dest_path))
    probed_height = dims[1] if dims else None

    assets = dict(project.quality_assets or init_quality_assets())
    assets[key] = {
        **empty_quality_asset(key),
        "status": "ready",
        "local_path": str(dest_path),
        "file_size_bytes": dest_path.stat().st_size,
        "height": probed_height or int(key),
        "host": host_for_quality(key),
        "host_status": "pending",
    }
    project.quality_assets = assets

    clip_key = quality_key(project.clip_source_quality or settings.clip_source_quality or "720")
    local_path = Path(project.local_video_path) if project.local_video_path else None
    if key == clip_key and (local_path is None or not local_path.is_file()):
        project.local_video_path = str(dest_path)

    project.updated_at = datetime.now(timezone.utc)
    await project.save()

    try:
        await trigger_distribute_project_qualities(project_id, qualities=[key], only_failed=False)
    except Exception:
        logger.exception("Quality host distribute trigger failed for project %s quality %s", project_id, key)

    return {
        "project_id": project_id,
        "quality": key,
        "status": "ready",
        "file_size_bytes": dest_path.stat().st_size,
        "host": host_for_quality(key),
        "message": f"{key}p saved. Uploading to host…",
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


async def _run_upload_pipeline_background(
    project_id: str,
    source_path: Path,
    extra_paths: list[Path] | None = None,
) -> None:
    from app.services.pipeline_runtime import release_pipeline

    project = await Project.get(PydanticObjectId(project_id))
    if not project:
        release_pipeline(project_id)
        return
    succeeded = False
    staging_paths = [source_path, *(extra_paths or [])]
    try:
        await _run_upload_pipeline(project_id, source_path, extra_paths)
        succeeded = True
    except Exception as exc:
        logger.exception("Upload pipeline failed for project %s", project_id)
        fresh = await Project.get(PydanticObjectId(project_id))
        if fresh:
            await _set_project_error(fresh, format_exception(exc))
    finally:
        release_pipeline(project_id)
        uploads_root = str((Path(settings.temp_dir) / "uploads").resolve())
        if succeeded:
            for path in staging_paths:
                if path.exists() and str(path.resolve()).startswith(uploads_root):
                    try:
                        path.unlink()
                    except OSError:
                        pass


async def retry_upload_processing(project: Project, background_tasks: BackgroundTasks) -> None:
    from app.services.pipeline_runtime import claim_pipeline, release_pipeline

    project_id = str(project.id)
    if not claim_pipeline(project_id, steal_after=30):
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
        background_tasks.add_task(_run_upload_pipeline_background, project_id, source_path)
        return

    if project.cloudinary_raw_url:
        project.status = ProjectStatus.PENDING
        metadata.pop("error_message", None)
        project.metadata = metadata
        project.updated_at = datetime.now(timezone.utc)
        await project.save()

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

    release_pipeline(project_id)
    await _set_project_error(
        project,
        "Original upload file is no longer on the server. Please upload the video again from the dashboard.",
    )
    raise FileNotFoundError(
        "Original upload file is no longer on the server. Please upload the video again from the dashboard."
    )
