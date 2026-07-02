import asyncio

from app.config import settings
from app.database import database, init_db


async def main() -> None:
    await init_db()
    print("db:", settings.mongodb_db_name)
    cols = await database.list_collection_names()
    print("collections:", cols)
    for name in cols:
        count = await database[name].count_documents({})
        print(f"  {name}: {count}")


if __name__ == "__main__":
    asyncio.run(main())
