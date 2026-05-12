import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel

from app.api.dependencies import get_current_user_id
from app.models.clip import Clip, ClipStatus, ClipType
from app.models.project import Project
from app.services.cloudinary_service import CloudinaryService
from app.tasks.clip_task import create_clip_task, run_clip_processing


router = APIRouter(tags=["clips"])


class CreateClipRequest(BaseModel):
    start_time: float
    end_time: float
    clip_type: ClipType
    label: str | None = None


class UpdateClipRequest(BaseModel):
    label: str


def serialize_document(doc: Any) -> dict[str, Any]:
    data = jsonable_encoder(doc.model_dump(by_alias=True))
    if "_id" in data:
        data["id"] = str(data.pop("_id"))
    return data


def validate_clip_window(payload: CreateClipRequest, project_duration_seconds: float | None) -> None:
    if payload.start_time < 0:
        raise HTTPException(status_code=422, detail="start_time must be >= 0")

    duration = payload.end_time - payload.start_time
    if duration < 1:
        raise HTTPException(status_code=422, detail="Clip duration must be >= 1 second")

    if payload.clip_type == ClipType.THIRTY_SECONDS and not (25 <= duration <= 35):
        raise HTTPException(status_code=422, detail="30s clip must be between 25 and 35 seconds")

    if payload.clip_type == ClipType.SIXTY_SECONDS and not (55 <= duration <= 65):
        raise HTTPException(status_code=422, detail="60s clip must be between 55 and 65 seconds")

    if payload.clip_type == ClipType.CUSTOM and not (30 <= duration <= 60):
        raise HTTPException(
            status_code=422,
            detail="Custom social snips must be between 30 and 60 seconds",
        )

    if project_duration_seconds is not None and payload.end_time > project_duration_seconds:
        raise HTTPException(status_code=422, detail="end_time cannot exceed project duration_seconds")


@router.post("/projects/{project_id}/clips", status_code=status.HTTP_201_CREATED)
async def create_project_clip(
    project_id: str,
    payload: CreateClipRequest,
    user_id: str = Depends(get_current_user_id),
):
    project = await Project.get(project_id)
    if not project or project.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    has_local = bool(project.local_video_path and Path(project.local_video_path).is_file())
    has_cloud_raw = bool(project.cloudinary_raw_url)
    if not has_local and not has_cloud_raw:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Video file is not available yet for clipping",
        )

    validate_clip_window(payload, project.duration_seconds)

    clip = Clip(
        project_id=project_id,
        user_id=user_id,
        label=payload.label,
        start_time=payload.start_time,
        end_time=payload.end_time,
        duration=payload.end_time - payload.start_time,
        clip_type=payload.clip_type,
        status=ClipStatus.PENDING,
        created_at=datetime.now(timezone.utc),
    )
    await clip.insert()

    clip_id_str = str(clip.id)
    response = serialize_document(clip)
    try:
        inspector = await asyncio.to_thread(create_clip_task.app.control.inspect, timeout=0.5)
        ping = await asyncio.to_thread(inspector.ping) if inspector else None
        if ping:
            task = create_clip_task.delay(project_id, clip_id_str)
            response["task_id"] = task.id
            response["execution_mode"] = "celery"
            return response
    except Exception:
        pass

    asyncio.create_task(run_clip_processing(project_id, clip_id_str))
    response["task_id"] = None
    response["execution_mode"] = "local-background"
    return response


@router.get("/projects/{project_id}/clips")
async def list_project_clips(project_id: str, user_id: str = Depends(get_current_user_id)):
    project = await Project.get(project_id)
    if not project or project.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    clips = await Clip.find(Clip.project_id == project_id, Clip.user_id == user_id).sort("start_time").to_list()
    return [serialize_document(clip) for clip in clips]


@router.get("/clips/{clip_id}")
async def get_clip(clip_id: str, user_id: str = Depends(get_current_user_id)):
    clip = await Clip.get(clip_id)
    if not clip or clip.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Clip not found")

    data = serialize_document(clip)
    data["clip_status"] = clip.status
    return data


@router.patch("/clips/{clip_id}")
async def update_clip_label(
    clip_id: str,
    payload: UpdateClipRequest,
    user_id: str = Depends(get_current_user_id),
):
    clip = await Clip.get(clip_id)
    if not clip or clip.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Clip not found")

    clip.label = payload.label
    await clip.save()
    return serialize_document(clip)


@router.delete("/clips/{clip_id}")
async def delete_clip(clip_id: str, user_id: str = Depends(get_current_user_id)):
    clip = await Clip.get(clip_id)
    if not clip or clip.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Clip not found")

    cloudinary_service = CloudinaryService()
    if clip.cloudinary_public_id:
        await cloudinary_service.delete_resource(clip.cloudinary_public_id, resource_type="video")
    await cloudinary_service.delete_by_prefix(
        f"projects/{clip.project_id}/clips/{clip_id}",
        resource_type="video",
    )
    await cloudinary_service.delete_by_prefix(
        f"projects/{clip.project_id}/clips/{clip_id}_thumb",
        resource_type="image",
    )

    await clip.delete()
    return {"deleted": True, "clip_id": clip_id}
