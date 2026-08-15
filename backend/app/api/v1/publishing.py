from typing import Any, Literal
from urllib.parse import urlparse, urlunparse
from html import escape
import json

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from celery.result import AsyncResult

from app.api.dependencies import get_current_user_id
from app.celery_worker import celery_app
from app.config import settings
from app.database import database
from app.models.clip import Clip, ClipStatus
from app.models.project import Project
from app.services.ppd_routing import (
    HOST_KEYS,
    HOST_LABELS,
    build_recommendations,
    get_clip_size_bytes,
    get_configured_hosts,
    get_host_service,
    get_bracket_table,
    resolve_hosts_for_size,
)
from app.services.publish_service import PublishService
from app.tasks.host_upload_task import trigger_host_upload
from app.tasks.publish_task import trigger_publish_all_instagram, trigger_publish_clip


router = APIRouter(tags=["publishing"])


def _oauth_redirect_uri(request: Request, route_name: str) -> str:
    if route_name == "instagram_oauth_callback":
        configured = (settings.instagram_redirect_uri or "").strip()
        if configured:
            return configured.rstrip("/")

    uri = str(request.url_for(route_name))
    parsed = urlparse(uri)
    host = parsed.hostname or "localhost"
    if host in {"127.0.0.1", "0.0.0.0"}:
        host = "localhost"
    scheme = parsed.scheme
    if host not in {"localhost", "127.0.0.1"}:
        scheme = "https"
    port = parsed.port
    if port in {80, 443}:
        port = None
    netloc = f"{host}:{port}" if port else host
    return urlunparse((scheme, netloc, parsed.path, "", "", ""))


def _oauth_result_page(platform: str, ok: bool, message: str = "") -> HTMLResponse:
    status_value = "connected" if ok else "error"
    labels = {"youtube": "YouTube", "instagram": "Instagram"}
    label = labels.get(platform, platform.title())
    heading = f"{label} connected" if ok else f"{label} connection failed"
    body = message.strip() or ("You can close this window." if ok else "Please close this window and try again.")
    payload = json.dumps(
        {
            "type": "oauth-complete",
            "platform": platform,
            "status": status_value,
            "message": body,
        }
    )
    html = f"""<!doctype html>
<html>
  <head><meta charset="utf-8"><title>{escape(heading)}</title></head>
  <body style="font-family: sans-serif; padding: 24px;">
    <h1>{escape(heading)}</h1>
    <p>{escape(body)}</p>
    <script>
      try {{
        if (window.opener) {{
          window.opener.postMessage({payload}, "*");
        }}
      }} catch (e) {{}}
      window.close();
    </script>
  </body>
</html>"""
    return HTMLResponse(html)


class PublishBody(BaseModel):
    title: str = ""
    description: str = ""
    clip_ids: list[str] | None = None
    recommended_only: bool = True


class DistributeBody(BaseModel):
    hosts: list[str] | None = None
    mode: Literal["auto", "manual"] = "auto"


@router.post("/auth/youtube")
async def initiate_youtube_oauth(
    request: Request,
    user_id: str = Depends(get_current_user_id),
):
    publish_service = PublishService()
    redirect_uri = _oauth_redirect_uri(request, "youtube_oauth_callback")
    try:
        auth_url = await publish_service.create_youtube_oauth_url(user_id=user_id, redirect_uri=redirect_uri)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return {"platform": "youtube", "auth_url": auth_url}


@router.get("/auth/youtube/callback", name="youtube_oauth_callback")
async def youtube_oauth_callback(
    code: str | None = Query(None),
    state: str | None = Query(None),
    error: str | None = Query(None),
    error_description: str | None = Query(None),
):
    if error:
        return _oauth_result_page("youtube", False, error_description or error)
    if not code or not state:
        return _oauth_result_page("youtube", False, "Missing OAuth code or state")
    try:
        await PublishService().complete_youtube_oauth(state=state, code=code)
    except Exception as exc:
        return _oauth_result_page("youtube", False, str(exc))
    return _oauth_result_page("youtube", True)


@router.post("/auth/instagram")
async def initiate_instagram_oauth(
    request: Request,
    user_id: str = Depends(get_current_user_id),
):
    publish_service = PublishService()
    redirect_uri = _oauth_redirect_uri(request, "instagram_oauth_callback")
    try:
        auth_url = await publish_service.create_instagram_oauth_url(user_id=user_id, redirect_uri=redirect_uri)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return {"platform": "instagram", "auth_url": auth_url}


@router.get("/auth/instagram/callback", name="instagram_oauth_callback")
async def instagram_oauth_callback(
    code: str | None = Query(None),
    state: str | None = Query(None),
    error: str | None = Query(None),
    error_description: str | None = Query(None),
    error_message: str | None = Query(None),
):
    if error:
        return _oauth_result_page("instagram", False, error_description or error_message or error)
    if not code or not state:
        return _oauth_result_page("instagram", False, "Missing OAuth code or state")
    try:
        await PublishService().complete_instagram_oauth(state=state, code=code)
    except Exception as exc:
        return _oauth_result_page("instagram", False, str(exc))
    return _oauth_result_page("instagram", True)


@router.get("/auth/status")
async def get_auth_status(user_id: str = Depends(get_current_user_id)):
    tokens = database["user_tokens"]
    youtube = await tokens.find_one({"user_id": user_id, "platform": "youtube"})
    instagram = await tokens.find_one({"user_id": user_id, "platform": "instagram"})
    return {
        "youtube": bool(youtube and youtube.get("access_token")),
        "instagram": bool(instagram and instagram.get("access_token") and instagram.get("ig_user_id")),
        "hosts": {key: get_host_service(key).is_configured() for key in HOST_KEYS},
        "cloudinary_configured": bool(
            settings.cloudinary_cloud_name and settings.cloudinary_api_key and settings.cloudinary_api_secret
        ),
    }


@router.get("/distribute/hosts")
async def get_distribute_hosts(user_id: str = Depends(get_current_user_id)):
    _ = user_id
    return {
        "hosts": [
            {
                "key": key,
                "label": HOST_LABELS[key],
                "configured": get_host_service(key).is_configured(),
            }
            for key in HOST_KEYS
        ],
        "brackets": get_bracket_table(),
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
    queued = await trigger_publish_clip(
        "youtube",
        clip_id,
        user_id,
        payload.title,
        payload.description,
    )
    clip.publish_task_id = queued["task_id"]
    clip.publish_platform = "youtube"
    clip.publish_status = "queued"
    await clip.save()
    return {"task_id": queued["task_id"], "status": "queued", "execution_mode": queued["execution_mode"]}


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
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Caption is required. Fetch one from the copy pool or write your own.",
        )
    if not title:
        title = (clip.label or "").strip()

    queued = await trigger_publish_clip(
        "instagram",
        clip_id,
        user_id,
        title,
        description,
    )
    clip.publish_task_id = queued["task_id"]
    clip.publish_platform = "instagram"
    clip.publish_status = "queued"
    await clip.save()
    return {
        "task_id": queued["task_id"],
        "status": "queued",
        "execution_mode": queued["execution_mode"],
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
    ).sort("+start_time").to_list()
    publishable = [c for c in ready_clips if c.cloudinary_clip_url]
    if not publishable:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No ready clips with Cloudinary URLs available to publish",
        )

    payload = body or PublishBody()
    title = payload.title.strip() or (project.title or "")
    description = payload.description.strip()
    if not description:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Caption is required. Fetch one from the copy pool or write your own.",
        )

    selected = publishable
    selection_mode = "all"
    if payload.clip_ids:
        wanted = {cid.strip() for cid in payload.clip_ids if cid and cid.strip()}
        by_id = {str(c.id): c for c in publishable}
        missing = sorted(wanted - set(by_id.keys()))
        if missing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unknown or unpublishable clip_ids: {', '.join(missing[:8])}",
            )
        selected = [by_id[cid] for cid in wanted if cid in by_id]
        # Preserve chronological order
        selected.sort(key=lambda c: float(c.start_time or 0.0))
        selection_mode = "selected"
    elif payload.recommended_only:
        recommended = [c for c in publishable if c.is_recommended]
        if not recommended:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "No recommended clips available. "
                    "Regenerate clips to compute interest scores, or publish with recommended_only=false."
                ),
            )
        selected = recommended
        selection_mode = "recommended"

    if not selected:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No clips matched the publish selection",
        )

    clip_ids = [str(c.id) for c in selected]
    queued = await trigger_publish_all_instagram(project_id, user_id, title, description, clip_ids)
    for clip in selected:
        clip.publish_task_id = queued["task_id"]
        clip.publish_platform = "instagram"
        clip.publish_status = "queued"
        await clip.save()

    return {
        "task_id": queued["task_id"],
        "status": "queued",
        "execution_mode": queued["execution_mode"],
        "clip_count": len(selected),
        "clip_ids": clip_ids,
        "selection_mode": selection_mode,
        "delay_seconds": settings.instagram_publish_delay_seconds,
        "using_copy_pool_caption": bool(description),
        "message": (
            f"Queued {len(selected)} clips for Instagram ({selection_mode}). "
            "Each Reel uses the same caption text."
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
            "interest_score": clip.interest_score,
            "is_recommended": bool(clip.is_recommended),
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
    description = payload.description.strip()
    if not description:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Caption is required. Fetch one from the copy pool or write your own.",
        )

    # Re-queue only failed clips via the same sequential publish-all worker path
    # by temporarily marking others as already published/idle isn't needed —
    # enqueue individual clip tasks so only failures are retried.
    queued_ids: list[str] = []
    for clip in retryable:
        clip_id = str(clip.id)
        queued = await trigger_publish_clip(
            "instagram",
            clip_id,
            user_id,
            (clip.label or title or ""),
            description,
        )
        clip.publish_task_id = queued["task_id"]
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
        if not clip.publish_status:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No publish task found")
        return {
            "task_id": None,
            "platform": clip.publish_platform,
            "state": clip.publish_status,
            "result": None,
            "publish_status": clip.publish_status,
            "published_media_id": clip.published_media_id,
            "published_url": clip.published_url,
        }

    result: Any = None
    task_state = clip.publish_status
    if not str(clip.publish_task_id).startswith("local"):
        try:
            task_result = AsyncResult(clip.publish_task_id, app=celery_app)
            task_state = task_result.state
            if task_result.ready():
                try:
                    result = task_result.result
                except Exception as exc:
                    result = {"error": str(exc)}
        except Exception:
            task_state = clip.publish_status

    return {
        "task_id": clip.publish_task_id,
        "platform": clip.publish_platform,
        "state": task_state,
        "result": result,
        "publish_status": clip.publish_status,
        "published_media_id": clip.published_media_id,
        "published_url": clip.published_url,
    }


@router.get("/clips/{clip_id}/distribute/recommendations")
async def get_distribute_recommendations(
    clip_id: str,
    user_id: str = Depends(get_current_user_id),
):
    clip = await Clip.get(clip_id)
    if not clip or clip.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Clip not found")

    size_bytes = get_clip_size_bytes(clip)
    if size_bytes is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Clip file size is unavailable. Ensure the clip has a local file or Cloudinary URL.",
        )

    return build_recommendations(size_bytes)


@router.post("/clips/{clip_id}/distribute")
async def distribute_clip(
    clip_id: str,
    body: DistributeBody,
    user_id: str = Depends(get_current_user_id),
):
    clip = await Clip.get(clip_id)
    if not clip or clip.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Clip not found")

    if not clip.local_clip_path and not clip.cloudinary_clip_url:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Clip has no local file or Cloudinary URL to upload from",
        )

    if body.mode == "manual" or body.hosts:
        selected = [h for h in (body.hosts or []) if h in HOST_KEYS]
    else:
        size_bytes = get_clip_size_bytes(clip)
        configured = get_configured_hosts()
        if size_bytes is None:
            selected = [h for h in HOST_KEYS if h in configured]
        else:
            routing = resolve_hosts_for_size(size_bytes, configured)
            selected = routing["recommended_hosts"]

    if not selected:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No valid configured hosts selected for distribute.",
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

    queued = await trigger_host_upload(clip_id, user_id, selected)
    clip.distribute_task_id = queued["task_id"]
    await clip.save()
    return {
        "task_id": queued["task_id"],
        "status": "queued",
        "hosts": selected,
        "mode": body.mode,
        "execution_mode": queued["execution_mode"],
    }


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
