from pydantic import BaseModel
from typing import Optional, List

class CaptionSchema(BaseModel):
    id: str
    start: float
    end: float
    text: str

    class Config:
        from_attributes = True

class ClipResponse(BaseModel):
    id: str
    job_id: str
    title: Optional[str]
    start_time: float
    end_time: float
    duration: float
    viral_score: float
    file_url: Optional[str]
    thumbnail_url: Optional[str]
    platform_format: str
    captions: List[CaptionSchema] = []

    class Config:
        from_attributes = True
