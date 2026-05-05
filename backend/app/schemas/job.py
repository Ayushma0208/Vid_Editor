from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class JobCreate(BaseModel):
    youtube_url: str

class JobResponse(BaseModel):
    id: str
    project_id: str
    status: str
    progress: int
    error_message: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True

class ProjectCreate(BaseModel):
    youtube_url: str

class ProjectResponse(BaseModel):
    id: str
    youtube_url: str
    title: Optional[str]
    thumbnail: Optional[str]
    created_at: datetime
    job: Optional[JobResponse] = None

    class Config:
        from_attributes = True
