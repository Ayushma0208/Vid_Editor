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
from app.services.ffmpeg_service import FfmpegService
from app.tasks.clip_task import start_local_clip_generation
from app.tasks.download_task import _set_project_error
from app.tasks.summary_task import trigger_project_summary
from app.utils.ffmpeg_utils import ffmpeg_available, ffmpeg_missing_message, format_exception, get_ffmpeg_path

logger = logging.getLogger(__name__)


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
        shutil.copy2(source_path, dest_path)
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

    metadata = project.metadata or {}
    metadata.pop("error_message", None)
    metadata["source"] = "upload"
    if thumb_ok:
        metadata["local_thumbnail_path"] = str(thumb_path)

    project.local_video_path = str(dest_path)
    project.duration_seconds = duration
    project.status = ProjectStatus.READY
    project.metadata = metadata
    project.updated_at = datetime.now(timezone.utc)
    await project.save()

    try:
        await trigger_project_summary(project_id)
    except Exception:
        logger.exception("Summary trigger failed for project %s", project_id)

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
    }


async def _run_upload_pipeline_background(project_id: str, source_path: Path) -> None:
    project = await Project.get(PydanticObjectId(project_id))
    if not project:
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
    metadata = project.metadata or {}
    original_filename = metadata.get("original_filename")
    if not original_filename:
        raise ValueError("Missing original upload filename for retry")

    source_path = staging_upload_path(project.user_id, str(original_filename))
    if not source_path.is_file() and project.local_video_path:
        source_path = Path(project.local_video_path)

    if not source_path.is_file():
        raise FileNotFoundError(
            "Original upload file is no longer on the server. Please upload the video again."
        )

    project.status = ProjectStatus.PENDING
    metadata.pop("error_message", None)
    project.metadata = metadata
    project.updated_at = datetime.now(timezone.utc)
    await project.save()

    background_tasks.add_task(_run_upload_pipeline_background, str(project.id), source_path)
