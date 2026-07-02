import asyncio

from app.database import init_db
from app.models.project import Project


async def main() -> None:
    await init_db()
    projects = await Project.find_all().sort("-created_at").limit(10).to_list()
    for p in projects:
        meta = p.metadata or {}
        print(str(p.id), p.status, p.title, meta.get("error_message", "")[:80])


if __name__ == "__main__":
    asyncio.run(main())
