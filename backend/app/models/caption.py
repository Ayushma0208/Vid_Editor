from datetime import datetime, timezone

from beanie import Document
from pydantic import BaseModel, Field


class CaptionLine(BaseModel):
    start: float
    end: float
    text: str


class CaptionStyle(BaseModel):
    font: str | None = None
    color: str | None = None
    position: str | None = None
    size: int | None = None


class Caption(Document):
    project_id: str
    clip_id: str | None = None
    user_id: str
    raw_text: str
    lines: list[CaptionLine] | None = None
    style: CaptionStyle | None = None
    version: int = 1
    ai_processed: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Settings:
        name = "captions"
