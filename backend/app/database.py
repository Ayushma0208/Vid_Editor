from beanie import init_beanie
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import ASCENDING, DESCENDING

from app.config import settings
from app.models.asset import Asset
from app.models.caption import Caption
from app.models.clip import Clip
from app.models.project import Project
from app.models.user import User


client = AsyncIOMotorClient(settings.mongodb_uri)
database = client[settings.mongodb_db_name]


async def get_database():
    return database


async def init_db() -> None:
    await init_beanie(
        database=database,
        document_models=[Project, Clip, Caption, Asset, User],
    )

    await database["projects"].create_index(
        [("user_id", ASCENDING), ("created_at", DESCENDING)],
        name="projects_user_created_desc_idx",
    )
    await database["clips"].create_index(
        [("project_id", ASCENDING), ("start_time", ASCENDING)],
        name="clips_project_start_asc_idx",
    )
    await database["captions"].create_index(
        [("project_id", ASCENDING), ("clip_id", ASCENDING)],
        name="captions_project_clip_idx",
    )
    await database["assets"].create_index(
        [("project_id", ASCENDING), ("source", ASCENDING), ("saved_at", DESCENDING)],
        name="assets_project_source_saved_desc_idx",
    )
    await database["users"].create_index(
        [("email", ASCENDING)],
        unique=True,
        name="users_email_unique_idx",
    )
