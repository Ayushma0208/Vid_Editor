from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class VideoModel(BaseModel):
    id: Optional[str] = Field(default=None, alias="_id")
    project_id: str
    source_url: str
    local_path: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
