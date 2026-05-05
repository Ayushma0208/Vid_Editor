from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from celery.result import AsyncResult

from app.api.dependencies import get_current_user_id
from app.celery_worker import celery_app
from app.models.clip import Clip
from app.services.publish_service import PublishService
from app.tasks.publish_task import publish_clip_task


router = APIRouter(tags=["publishing"])


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


@router.post("/clips/{clip_id}/publish/youtube")
async def publish_clip_to_youtube(
    clip_id: str,
    user_id: str = Depends(get_current_user_id),
):
    clip = await Clip.get(clip_id)
    if not clip or clip.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Clip not found")

    task = publish_clip_task.delay("youtube", clip_id, user_id)
    clip.publish_task_id = task.id
    clip.publish_platform = "youtube"
    clip.publish_status = "queued"
    await clip.save()
    return {"task_id": task.id, "status": "queued"}


@router.post("/clips/{clip_id}/publish/instagram")
async def publish_clip_to_instagram(
    clip_id: str,
    user_id: str = Depends(get_current_user_id),
):
    clip = await Clip.get(clip_id)
    if not clip or clip.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Clip not found")

    task = publish_clip_task.delay("instagram", clip_id, user_id)
    clip.publish_task_id = task.id
    clip.publish_platform = "instagram"
    clip.publish_status = "queued"
    await clip.save()
    return {"task_id": task.id, "status": "queued"}


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
    return {
        "task_id": clip.publish_task_id,
        "platform": clip.publish_platform,
        "state": task_result.state,
        "result": task_result.result if task_result.ready() else None,
        "publish_status": clip.publish_status,
        "published_media_id": clip.published_media_id,
        "published_url": clip.published_url,
    }
