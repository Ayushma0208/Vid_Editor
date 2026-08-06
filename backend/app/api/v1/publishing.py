from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from celery.result import AsyncResult

from app.api.dependencies import get_current_user_id
from app.celery_worker import celery_app
from app.config import settings
from app.database import database
from app.models.clip import Clip, ClipStatus
from app.models.project import Project
from app.services.krakenfiles_service import KrakenFilesService
from app.services.publish_service import PublishService
from app.services.up4ever_service import Up4everService
from app.services.uploadrar_service import UploadrarService
from app.tasks.host_upload_task import HOST_KEYS, host_upload_task
from app.tasks.publish_task import publish_all_instagram_task, publish_clip_task


router = APIRouter(tags=["publishing"])


class PublishBody(BaseModel):
    title: str = ""
    description: str = ""


class DistributeBody(BaseModel):
    hosts: list[str] = Field(default_factory=lambda: list(HOST_KEYS))


@router.post("/auth/youtube")
async def initiate_youtube_oauth(
    request: Request,
    user_id: str = Depends(get_current_user_id),
):
    publish_service = PublishService()
    redirect_uri = str(request.url_for("youtube_oauth_callback"))
    auth_url = await publish_service.create_youtube_oauth_url(user_id=user_id, redirect_uri=redirect_uri)
    return {"platform": "youtube", "auth_url": auth_url}


@router.get("/auth/youtube/callback", name="youtube_oauth_callback")
async def youtube_oauth_callback(
    code: str = Query(...),
    state: str = Query(...),
):
    try:
        result = await PublishService().complete_youtube_oauth(state=state, code=code)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return result


@router.post("/auth/instagram")
async def initiate_instagram_oauth(
    request: Request,
    user_id: str = Depends(get_current_user_id),
):
    publish_service = PublishService()
    redirect_uri = str(request.url_for("instagram_oauth_callback"))
    auth_url = await publish_service.create_instagram_oauth_url(user_id=user_id, redirect_uri=redirect_uri)
    return {"platform": "instagram", "auth_url": auth_url}


@router.get("/auth/instagram/callback", name="instagram_oauth_callback")
async def instagram_oauth_callback(
    code: str = Query(...),
    state: str = Query(...),
):
    try:
        result = await PublishService().complete_instagram_oauth(state=state, code=code)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return result


@router.get("/auth/status")
async def get_auth_status(user_id: str = Depends(get_current_user_id)):
    tokens = database["user_tokens"]
    youtube = await tokens.find_one({"user_id": user_id, "platform": "youtube"})
    instagram = await tokens.find_one({"user_id": user_id, "platform": "instagram"})
    return {
        "youtube": bool(youtube and youtube.get("access_token")),
        "instagram": bool(instagram and instagram.get("access_token") and instagram.get("ig_user_id")),
        "hosts": {
            "krakenfiles": KrakenFilesService().is_configured(),
            "uploadrar": UploadrarService().is_configured(),
            "up4ever": Up4everService().is_configured(),
        },
        "cloudinary_configured": bool(
            settings.cloudinary_cloud_name and settings.cloudinary_api_key and settings.cloudinary_api_secret
        ),
    }


@router.get("/distribute/hosts")
async def get_distribute_hosts(user_id: str = Depends(get_current_user_id)):
    _ = user_id
    return {
        "hosts": [
            {"key": "krakenfiles", "label": "KrakenFiles", "configured": KrakenFilesService().is_configured()},
            {"key": "uploadrar", "label": "Uploadrar", "configured": UploadrarService().is_configured()},
            {"key": "up4ever", "label": "Up-4ever", "configured": Up4everService().is_configured()},
        ]
    }


@router.post("/clips/{clip_id}/publish/youtube")
async def publish_clip_to_youtube(
    clip_id: str,
    body: PublishBody | None = None,
    user_id: str = Depends(get_current_user_id),
):
    clip = await Clip.get(clip_id)
    if not clip or clip.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Clip not found")
    if not clip.cloudinary_clip_url:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Clip Cloudinary URL is missing. Re-process the clip or configure Cloudinary.",
        )

    payload = body or PublishBody()
    task = publish_clip_task.delay(
        "youtube",
        clip_id,
        user_id,
        payload.title,
        payload.description,
    )
    clip.publish_task_id = task.id
    clip.publish_platform = "youtube"
    clip.publish_status = "queued"
    await clip.save()
    return {"task_id": task.id, "status": "queued"}


@router.post("/clips/{clip_id}/publish/instagram")
async def publish_clip_to_instagram(
    clip_id: str,
    body: PublishBody | None = None,
    user_id: str = Depends(get_current_user_id),
):
    clip = await Clip.get(clip_id)
    if not clip or clip.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Clip not found")
    if not clip.cloudinary_clip_url:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Clip Cloudinary URL is missing. Instagram requires a public video URL.",
        )

    payload = body or PublishBody()
    title = payload.title.strip()
    description = payload.description.strip()
    if not description:
        project = await Project.get(clip.project_id)
        if project and project.summary:
            description = project.summary
    if not title:
        title = (clip.label or "").strip()

    task = publish_clip_task.delay(
        "instagram",
        clip_id,
        user_id,
        title,
        description,
    )
    clip.publish_task_id = task.id
    clip.publish_platform = "instagram"
    clip.publish_status = "queued"
    await clip.save()
    return {
        "task_id": task.id,
        "status": "queued",
        "caption_preview": "\n\n".join([p for p in (title, description) if p])[:500],
    }


@router.post("/projects/{project_id}/publish/instagram")
async def publish_all_project_clips_to_instagram(
    project_id: str,
    body: PublishBody | None = None,
    user_id: str = Depends(get_current_user_id),
):
    project = await Project.get(project_id)
    if not project or project.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    tokens = database["user_tokens"]
    instagram = await tokens.find_one({"user_id": user_id, "platform": "instagram"})
    if not instagram or not instagram.get("access_token") or not instagram.get("ig_user_id"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Instagram account is not connected",
        )

    ready_clips = await Clip.find(
        Clip.project_id == project_id,
        Clip.user_id == user_id,
        Clip.status == ClipStatus.READY,
    ).to_list()
    publishable = [c for c in ready_clips if c.cloudinary_clip_url]
    if not publishable:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No ready clips with Cloudinary URLs available to publish",
        )

    payload = body or PublishBody()
    title = payload.title.strip() or (project.title or "")
    description = payload.description.strip() or (project.summary or "")

    task = publish_all_instagram_task.delay(project_id, user_id, title, description)
    for clip in publishable:
        clip.publish_task_id = task.id
        clip.publish_platform = "instagram"
        clip.publish_status = "queued"
        await clip.save()

    return {
        "task_id": task.id,
        "status": "queued",
        "clip_count": len(publishable),
        "delay_seconds": settings.instagram_publish_delay_seconds,
        "using_full_video_summary": bool(description),
        "message": (
            f"Queued {len(publishable)} clips for Instagram. "
            "Each Reel caption uses the full-video summary."
        ),
    }


def _instagram_publish_counts(clips: list[Clip]) -> dict[str, int]:
    counts = {
        "total": 0,
        "publishable": 0,
        "queued": 0,
        "processing": 0,
        "published": 0,
        "error": 0,
        "idle": 0,
    }
    for clip in clips:
        counts["total"] += 1
        if clip.cloudinary_clip_url and clip.status == ClipStatus.READY:
            counts["publishable"] += 1
        status_value = (clip.publish_status or "").lower().strip()
        if status_value in ("queued", "processing", "published", "error"):
            counts[status_value] += 1
        else:
            counts["idle"] += 1
    counts["in_flight"] = counts["queued"] + counts["processing"]
    counts["done"] = counts["published"] + counts["error"]
    return counts


@router.get("/projects/{project_id}/publish/instagram/status")
async def get_project_instagram_publish_status(
    project_id: str,
    user_id: str = Depends(get_current_user_id),
):
    project = await Project.get(project_id)
    if not project or project.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    clips = await Clip.find(
        Clip.project_id == project_id,
        Clip.user_id == user_id,
        Clip.status == ClipStatus.READY,
    ).sort("+start_time").to_list()

    counts = _instagram_publish_counts(clips)
    items = [
        {
            "clip_id": str(clip.id),
            "label": clip.label,
            "start_time": clip.start_time,
            "publish_status": clip.publish_status,
            "published_url": clip.published_url,
            "has_cloudinary_url": bool(clip.cloudinary_clip_url),
        }
        for clip in clips
    ]
    return {
        "project_id": project_id,
        "counts": counts,
        "delay_seconds": settings.instagram_publish_delay_seconds,
        "clips": items,
        "active": counts["in_flight"] > 0,
    }


@router.post("/projects/{project_id}/publish/instagram/retry")
async def retry_failed_instagram_publishes(
    project_id: str,
    body: PublishBody | None = None,
    user_id: str = Depends(get_current_user_id),
):
    project = await Project.get(project_id)
    if not project or project.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    tokens = database["user_tokens"]
    instagram = await tokens.find_one({"user_id": user_id, "platform": "instagram"})
    if not instagram or not instagram.get("access_token") or not instagram.get("ig_user_id"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Instagram account is not connected",
        )

    failed = await Clip.find(
        Clip.project_id == project_id,
        Clip.user_id == user_id,
        Clip.status == ClipStatus.READY,
        Clip.publish_status == "error",
    ).sort("+start_time").to_list()
    retryable = [c for c in failed if c.cloudinary_clip_url]
    if not retryable:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No failed Instagram publishes to retry",
        )

    payload = body or PublishBody()
    title = payload.title.strip() or (project.title or "")
    description = payload.description.strip() or (project.summary or "")

    # Re-queue only failed clips via the same sequential publish-all worker path
    # by temporarily marking others as already published/idle isn't needed —
    # enqueue individual clip tasks so only failures are retried.
    queued_ids: list[str] = []
    for clip in retryable:
        clip_id = str(clip.id)
        task = publish_clip_task.delay(
            "instagram",
            clip_id,
            user_id,
            (clip.label or title or ""),
            description,
        )
        clip.publish_task_id = task.id
        clip.publish_platform = "instagram"
        clip.publish_status = "queued"
        await clip.save()
        queued_ids.append(clip_id)

    return {
        "status": "queued",
        "clip_count": len(queued_ids),
        "clip_ids": queued_ids,
        "message": f"Retrying {len(queued_ids)} failed Instagram publish(es).",
    }


@router.get("/clips/{clip_id}/publish/status")
async def get_publish_status(
    clip_id: str,
    user_id: str = Depends(get_current_user_id),
):
    clip = await Clip.get(clip_id)
    if not clip or clip.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Clip not found")
    if not clip.publish_task_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No publish task found")

    task_result = AsyncResult(clip.publish_task_id, app=celery_app)
    result: Any = None
    if task_result.ready():
        try:
            result = task_result.result
        except Exception as exc:
            result = {"error": str(exc)}

    return {
        "task_id": clip.publish_task_id,
        "platform": clip.publish_platform,
        "state": task_result.state,
        "result": result,
        "publish_status": clip.publish_status,
        "published_media_id": clip.published_media_id,
        "published_url": clip.published_url,
    }


@router.post("/clips/{clip_id}/distribute")
async def distribute_clip(
    clip_id: str,
    body: DistributeBody,
    user_id: str = Depends(get_current_user_id),
):
    clip = await Clip.get(clip_id)
    if not clip or clip.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Clip not found")

    selected = [h for h in body.hosts if h in HOST_KEYS]
    if not selected:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No valid hosts selected")

    if not clip.local_clip_path and not clip.cloudinary_clip_url:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Clip has no local file or Cloudinary URL to upload from",
        )

    uploads = dict(clip.host_uploads or {})
    for host in selected:
        uploads[host] = {
            **uploads.get(host, {}),
            "status": "queued",
            "error": None,
            "updated_at": None,
        }
    clip.host_uploads = uploads

    task = host_upload_task.delay(clip_id, user_id, selected)
    clip.distribute_task_id = task.id
    await clip.save()
    return {"task_id": task.id, "status": "queued", "hosts": selected}


@router.get("/clips/{clip_id}/distribute/status")
async def get_distribute_status(
    clip_id: str,
    user_id: str = Depends(get_current_user_id),
):
    clip = await Clip.get(clip_id)
    if not clip or clip.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Clip not found")

    task_state = None
    if clip.distribute_task_id:
        task_state = AsyncResult(clip.distribute_task_id, app=celery_app).state

    return {
        "task_id": clip.distribute_task_id,
        "state": task_state,
        "host_uploads": clip.host_uploads or {},
    }
