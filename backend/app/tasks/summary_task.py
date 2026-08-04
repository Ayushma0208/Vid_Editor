import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from beanie import PydanticObjectId

from app.celery_worker import celery_app
import app.celery_worker as cw
from app.config import settings
from app.models.project import Project, SummaryStatus
from app.services.summary_service import SummaryService
from app.utils.celery_utils import celery_workers_available
from app.utils.ffmpeg_utils import format_exception

logger = logging.getLogger(__name__)


async def run_project_summary(project_id: str) -> dict[str, Any]:
    project = await Project.get(PydanticObjectId(project_id))
    if not project:
        raise RuntimeError("Project not found")

    project.summary_status = SummaryStatus.PROCESSING
    project.summary_error = None
    project.updated_at = datetime.now(timezone.utc)
    await project.save()

    work_dir = Path(settings.temp_dir) / project_id
    work_dir.mkdir(parents=True, exist_ok=True)

    try:
        summary = await SummaryService().generate_project_summary(
            title=project.title,
            local_video_path=project.local_video_path,
            metadata=project.metadata,
            duration_seconds=project.duration_seconds,
            work_dir=work_dir,
        )
        project.summary = summary
        project.summary_status = SummaryStatus.READY
        project.summary_error = None
        project.updated_at = datetime.now(timezone.utc)
        await project.save()
        return {
            "project_id": project_id,
            "summary_status": project.summary_status.value,
            "summary": project.summary,
        }
    except Exception as exc:
        logger.exception("Summary generation failed for project %s", project_id)
        project.summary_status = SummaryStatus.ERROR
        project.summary_error = format_exception(exc)
        project.updated_at = datetime.now(timezone.utc)
        await project.save()
        raise


async def trigger_project_summary(project_id: str) -> dict[str, Any]:
    project = await Project.get(PydanticObjectId(project_id))
    if project:
        project.summary_status = SummaryStatus.PENDING
        project.summary_error = None
        project.updated_at = datetime.now(timezone.utc)
        await project.save()

    if await celery_workers_available():
        try:
            task = generate_project_summary_task.delay(project_id)
            return {
                "task_id": task.id,
                "execution_mode": "celery",
                "summary_status": SummaryStatus.PENDING.value,
            }
        except Exception:
            logger.exception("Failed to enqueue summary Celery task for %s", project_id)

    asyncio.create_task(run_project_summary(project_id))
    return {
        "task_id": None,
        "execution_mode": "local-background",
        "summary_status": SummaryStatus.PENDING.value,
    }


@celery_app.task(name="generate_project_summary_task")
def generate_project_summary_task(project_id: str):
    loop = cw.worker_loop if cw.worker_loop is not None else asyncio.get_event_loop()
    return loop.run_until_complete(run_project_summary(project_id))
