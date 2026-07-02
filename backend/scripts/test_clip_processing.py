import asyncio
import traceback

from app.database import init_db
from app.tasks.clip_task import run_clip_processing


async def main() -> None:
    await init_db()
    project_id = "6a270e9f50ab8a6d1ea3cb80"
    clip_id = "6a2713504c72dbfbb32a7702"
    try:
        result = await run_clip_processing(project_id, clip_id)
        print("OK", result)
    except Exception as exc:
        print("FAILED", type(exc).__name__, exc)
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
