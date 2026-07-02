import asyncio

from app.database import init_db
from app.models.clip import Clip
from app.models.project import Project


async def main() -> None:
    await init_db()
    clips = await Clip.find_all().sort("-created_at").limit(20).to_list()
    for c in clips:
        print(c.id, c.project_id[:8], c.label, c.status, c.start_time, c.end_time)


if __name__ == "__main__":
    asyncio.run(main())
