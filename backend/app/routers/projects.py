from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models.project import Project
from app.models.job import Job
from app.schemas.job import ProjectCreate, ProjectResponse
from app.utils.jwt_utils import get_current_user_id
from app.workers.pipeline import run_pipeline
import uuid

router = APIRouter(prefix="/projects", tags=["projects"])

@router.post("/", response_model=ProjectResponse)
async def create_project(
    body: ProjectCreate,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    project = Project(id=str(uuid.uuid4()), user_id=user_id, youtube_url=body.youtube_url)
    db.add(project)
    job = Job(id=str(uuid.uuid4()), project_id=project.id, status="queued", progress=0)
    db.add(job)
    await db.commit()
    await db.refresh(project)
    await db.refresh(job)

    task = run_pipeline.delay(job.id)
    job.celery_task_id = task.id
    await db.commit()

    return project

@router.get("/", response_model=list[ProjectResponse])
async def list_projects(
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    result = await db.execute(
        select(Project).where(Project.user_id == user_id).order_by(Project.created_at.desc())
    )
    return result.scalars().all()

@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    result = await db.execute(select(Project).where(Project.id == project_id, Project.user_id == user_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(404, "Project not found")
    return project
