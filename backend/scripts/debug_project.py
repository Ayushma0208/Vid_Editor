"""Debug a failed upload project. Usage: python scripts/debug_project.py <project_id>"""
import asyncio
import sys
import traceback
from pathlib import Path

from beanie import PydanticObjectId

from app.database import init_db
from app.models.project import Project
from app.tasks.upload_task import retry_upload_processing, staging_upload_path
from app.utils.ffmpeg_utils import ffmpeg_available, get_ffmpeg_path, get_ffprobe_path


async def main(project_id: str) -> None:
    await init_db()
    print("ffmpeg available:", ffmpeg_available())
    print("ffmpeg:", get_ffmpeg_path())
    print("ffprobe:", get_ffprobe_path())

    project = await Project.get(PydanticObjectId(project_id))
    if not project:
        print("Project not found")
        return

    print("status:", project.status)
    print("local_video_path:", project.local_video_path)
    meta = project.metadata or {}
    print("error_message:", meta.get("error_message"))
    print("auto_clip_warning:", meta.get("auto_clip_warning"))
    print("original_filename:", meta.get("original_filename"))

    staging = staging_upload_path(project.user_id, str(meta.get("original_filename", "")))
    print("staging path:", staging, "exists:", staging.is_file())
    if project.local_video_path:
        p = Path(project.local_video_path)
        print("local path exists:", p.is_file(), p)

    print("\n--- retry ---")
    try:
        await retry_upload_processing(project)
        print("retry started (background)")
        await asyncio.sleep(5)
        fresh = await Project.get(PydanticObjectId(project_id))
        if fresh:
            print("new status:", fresh.status)
            print("new error:", (fresh.metadata or {}).get("error_message"))
    except Exception:
        traceback.print_exc()


if __name__ == "__main__":
    pid = sys.argv[1] if len(sys.argv) > 1 else "6a26fe535de4eba94976f90a"
    asyncio.run(main(pid))
