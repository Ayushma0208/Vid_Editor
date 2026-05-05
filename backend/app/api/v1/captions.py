from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel

from app.api.dependencies import get_current_user_id
from app.models.caption import Caption, CaptionLine, CaptionStyle
from app.models.clip import Clip
from app.models.project import Project


router = APIRouter(tags=["captions"])


class CreateCaptionRequest(BaseModel):
    raw_text: str
    clip_id: str | None = None
    lines: list[CaptionLine] | None = None
    style: CaptionStyle | None = None


class UpdateCaptionRequest(BaseModel):
    raw_text: str | None = None
    lines: list[CaptionLine] | None = None
    style: CaptionStyle | None = None
    ai_processed: bool | None = None


def serialize_document(doc: Any) -> dict[str, Any]:
    return jsonable_encoder(doc.model_dump(by_alias=True))


@router.post("/projects/{project_id}/captions", status_code=status.HTTP_201_CREATED)
async def create_caption(
    project_id: str,
    payload: CreateCaptionRequest,
    user_id: str = Depends(get_current_user_id),
):
    project = await Project.get(project_id)
    if not project or project.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    if payload.clip_id:
        clip = await Clip.get(payload.clip_id)
        if not clip or clip.project_id != project_id or clip.user_id != user_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Clip not found")

    now = datetime.now(timezone.utc)
    caption = Caption(
        project_id=project_id,
        clip_id=payload.clip_id,
        user_id=user_id,
        raw_text=payload.raw_text,
        lines=payload.lines,
        style=payload.style,
        version=1,
        ai_processed=False,
        created_at=now,
        updated_at=now,
    )
    await caption.insert()
    return serialize_document(caption)


@router.get("/projects/{project_id}/captions")
async def list_project_captions(
    project_id: str,
    clip_id: str | None = Query(default=None),
    user_id: str = Depends(get_current_user_id),
):
    project = await Project.get(project_id)
    if not project or project.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    query = [Caption.project_id == project_id, Caption.user_id == user_id]
    if clip_id is not None:
        query.append(Caption.clip_id == clip_id)

    captions = await Caption.find(*query).sort("-updated_at").to_list()
    return [serialize_document(caption) for caption in captions]


@router.get("/captions/{caption_id}")
async def get_caption(caption_id: str, user_id: str = Depends(get_current_user_id)):
    caption = await Caption.get(caption_id)
    if not caption or caption.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Caption not found")
    return serialize_document(caption)


@router.patch("/captions/{caption_id}")
async def update_caption(
    caption_id: str,
    payload: UpdateCaptionRequest,
    user_id: str = Depends(get_current_user_id),
):
    caption = await Caption.get(caption_id)
    if not caption or caption.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Caption not found")

    if payload.raw_text is not None:
        caption.raw_text = payload.raw_text
    if payload.lines is not None:
        caption.lines = payload.lines
    if payload.style is not None:
        caption.style = payload.style
    if payload.ai_processed is not None:
        caption.ai_processed = payload.ai_processed

    caption.version += 1
    caption.updated_at = datetime.now(timezone.utc)
    await caption.save()
    return serialize_document(caption)


@router.delete("/captions/{caption_id}")
async def delete_caption(caption_id: str, user_id: str = Depends(get_current_user_id)):
    caption = await Caption.get(caption_id)
    if not caption or caption.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Caption not found")

    await caption.delete()
    return {"deleted": True, "caption_id": caption_id}
