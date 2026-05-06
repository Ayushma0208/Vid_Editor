import asyncio
from datetime import datetime, timezone
from pathlib import Path

from beanie import PydanticObjectId
from celery.exceptions import MaxRetriesExceededError

from app.celery_worker import celery_app
import app.celery_worker as cw
from app.config import settings
from app.models.project import Project, ProjectStatus
from app.services.ytdlp_service import YTDLPService

async def _set_project_error(project: Project, error_message: str) -> None:
    metadata = project.metadata or {}
    metadata["error_message"] = error_message
    project.metadata = metadata
    project.status = ProjectStatus.ERROR
    project.updated_at = datetime.now(timezone.utc)
    await project.save()

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

    # Save the local file path and mark as ready — no Cloudinary upload needed
    project.status = ProjectStatus.READY
    project.local_video_path = local_video_path
    metadata = project.metadata or {}
    metadata.pop("error_message", None)
    project.metadata = metadata
    project.updated_at = datetime.now(timezone.utc)
    await project.save()

    return {
        "project_id": project_id,
        "status": project.status.value,
        "local_video_path": project.local_video_path,
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
                await _set_project_error(project, str(exc))

        if cw.worker_loop is None:
            loop = asyncio.get_event_loop()
        else:
            loop = cw.worker_loop
        loop.run_until_complete(_mark_error())

        try:
            raise self.retry(exc=exc, countdown=30)
        except MaxRetriesExceededError:
            return {"project_id": project_id, "status": "error", "error_message": str(exc)}
