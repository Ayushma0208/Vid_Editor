from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models.clip import Clip
from app.models.job import Job
from app.models.project import Project
from app.schemas.clip import ClipResponse
from app.utils.jwt_utils import get_current_user_id

router = APIRouter(prefix="/clips", tags=["clips"])

@router.get("/job/{job_id}", response_model=list[ClipResponse])
async def get_clips_for_job(
    job_id: str,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    result = await db.execute(
        select(Clip).where(Clip.job_id == job_id).order_by(Clip.order_index)
    )
    return result.scalars().all()

@router.get("/{clip_id}", response_model=ClipResponse)
async def get_clip(
    clip_id: str,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    result = await db.execute(select(Clip).where(Clip.id == clip_id))
    clip = result.scalar_one_or_none()
    if not clip:
        raise HTTPException(404, "Clip not found")
    return clip
