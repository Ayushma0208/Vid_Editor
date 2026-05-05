from datetime import datetime, timezone
from enum import Enum

from beanie import Document
from pydantic import Field


class AssetSource(str, Enum):
    PEXELS = "pexels"
    PIXABAY = "pixabay"


class AssetType(str, Enum):
    IMAGE = "image"
    VIDEO = "video"


class Asset(Document):
    project_id: str
    user_id: str
    source: AssetSource
    source_id: str
    asset_type: AssetType
    url: str
    thumbnail_url: str | None = None
    query_used: str | None = None
    photographer: str | None = None
    saved_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Settings:
        name = "assets"
