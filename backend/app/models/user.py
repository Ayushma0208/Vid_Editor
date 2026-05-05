from datetime import datetime, timezone

from beanie import Document
from pydantic import Field


class User(Document):
    email: str
    hashed_password: str
    full_name: str | None = None
    is_active: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Settings:
        name = "users"
