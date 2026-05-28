from datetime import datetime, timezone
from enum import Enum

from beanie import Document
from pydantic import Field


class ClipType(str, Enum):
    THIRTY_SECONDS = "30s"
    SIXTY_SECONDS = "60s"
    CUSTOM = "custom"


class ClipStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    READY = "ready"
    ERROR = "error"


class Clip(Document):
    project_id: str
    user_id: str
    label: str | None = None
    start_time: float
    end_time: float
    duration: float
    clip_type: ClipType
    status: ClipStatus
    cloudinary_clip_url: str | None = None
    cloudinary_public_id: str | None = None
    thumbnail_url: str | None = None
    local_clip_path: str | None = None
    local_thumbnail_path: str | None = None
    publish_task_id: str | None = None
    publish_platform: str | None = None
    publish_status: str | None = None
    published_media_id: str | None = None
    published_url: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Settings:
        name = "clips"
