"""Re-process all failed upload projects that still have video files on disk."""
import asyncio

from beanie import PydanticObjectId

from app.database import init_db
from app.models.project import Project, ProjectStatus
from app.tasks.upload_task import _run_upload_pipeline_background, staging_upload_path


async def main() -> None:
    await init_db()
    projects = await Project.find(Project.status == ProjectStatus.ERROR).to_list()
    for project in projects:
        meta = project.metadata or {}
        if meta.get("source") != "upload":
            continue
        orig = meta.get("original_filename")
        if not orig:
            continue
        source = staging_upload_path(project.user_id, str(orig))
        if not source.is_file() and project.local_video_path:
            from pathlib import Path

            source = Path(project.local_video_path)
        if not source.is_file():
            print("skip (no file):", project.id, project.title)
            continue
        print("processing:", project.id, project.title)
        meta.pop("error_message", None)
        project.status = ProjectStatus.PENDING
        project.metadata = meta
        await project.save()
        await _run_upload_pipeline_background(str(project.id), source)
        fresh = await Project.get(PydanticObjectId(project.id))
        if fresh:
            print("  ->", fresh.status, (fresh.metadata or {}).get("error_message"))


if __name__ == "__main__":
    asyncio.run(main())
