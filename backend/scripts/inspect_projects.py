import asyncio
from pathlib import Path

from app.config import settings
from app.database import init_db
from app.models.project import Project
from app.tasks.upload_task import staging_upload_path


async def main() -> None:
    await init_db()
    projects = await Project.find_all().sort("-created_at").to_list()
    for p in projects:
        meta = p.metadata or {}
        orig = meta.get("original_filename")
        staging = staging_upload_path(p.user_id, str(orig)) if orig else None
        local = Path(p.local_video_path) if p.local_video_path else None
        print("---")
        print("id:", p.id)
        print("title:", p.title)
        print("status:", p.status)
        print("user_id:", p.user_id)
        print("error:", meta.get("error_message"))
        print("original:", orig)
        print("staging exists:", staging.is_file() if staging else None, staging)
        print("local exists:", local.is_file() if local else None, local)


if __name__ == "__main__":
    asyncio.run(main())
