from datetime import datetime, timezone
from enum import Enum
from typing import Any

from beanie import Document
from pydantic import Field


class ProjectStatus(str, Enum):
    PENDING = "pending"
    DOWNLOADING = "downloading"
    READY = "ready"
    ERROR = "error"


class SummaryStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    READY = "ready"
    ERROR = "error"


class Project(Document):
    user_id: str
    title: str
    yt_url: str
    yt_video_id: str
    status: ProjectStatus
    cloudinary_raw_url: str | None = None
    local_video_path: str | None = None
    cloudinary_folder: str
    duration_seconds: float | None = None
    thumbnail_url: str | None = None
    summary: str | None = None
    summary_status: SummaryStatus | None = None
    summary_error: str | None = None
    # Per-height full-movie assets: keys "240"|"480"|"720"|"1080"
    quality_assets: dict[str, dict[str, Any]] = Field(default_factory=dict)
    clip_source_quality: str = "720"
    clips_expire_at: datetime | None = None
    metadata: dict[str, Any] | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Settings:
        name = "projects"
