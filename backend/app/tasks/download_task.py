import asyncio
from datetime import datetime, timezone
from pathlib import Path

from asgiref.sync import async_to_sync
from beanie import PydanticObjectId
from celery.exceptions import MaxRetriesExceededError

from app.celery_worker import celery_app
from app.config import settings
from app.models.project import Project, ProjectStatus
from app.services.cloudinary_service import CloudinaryService
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
    cloudinary_service = CloudinaryService()

    output_template = str(Path(settings.temp_dir) / project_id / "raw_video.%(ext)s")
    local_video_path = await ytdlp_service.download_video(
        url=video_url,
        output_path=output_template,
        quality="1080p",
    )

    cloudinary_folder = f"projects/{project_id}/raw"
    upload_result = await cloudinary_service.upload_video(
        file_path=local_video_path,
        folder=cloudinary_folder,
    )

    project.status = ProjectStatus.READY
    project.cloudinary_raw_url = upload_result.get("secure_url") or upload_result.get("url")
    project.cloudinary_folder = cloudinary_folder
    metadata = project.metadata or {}
    metadata.pop("error_message", None)
    project.metadata = metadata
    project.updated_at = datetime.now(timezone.utc)
    await project.save()

    file_to_delete = Path(local_video_path)
    if file_to_delete.exists():
        file_to_delete.unlink()

    return {
        "project_id": project_id,
        "status": project.status.value,
        "cloudinary_raw_url": project.cloudinary_raw_url,
        "cloudinary_folder": project.cloudinary_folder,
    }


@celery_app.task(bind=True, name="download_video_task", max_retries=2)
def download_video_task(self, project_id: str, video_url: str):
    try:
        return async_to_sync(_run_download_pipeline)(project_id, video_url)
    except Exception as exc:
        async def _mark_error() -> None:
            project = await Project.get(PydanticObjectId(project_id))
            if project:
                await _set_project_error(project, str(exc))

        async_to_sync(_mark_error)()

        try:
            raise self.retry(exc=exc, countdown=30)
        except MaxRetriesExceededError:
            return {"project_id": project_id, "status": "error", "error_message": str(exc)}
