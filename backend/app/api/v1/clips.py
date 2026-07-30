import asyncio
import io
import re
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
from starlette.background import BackgroundTask

from app.api.dependencies import get_current_user_id, resolve_user_id_from_token
from app.models.clip import Clip, ClipStatus, ClipType
from app.models.project import Project
from app.services.cloudinary_service import CloudinaryService
from app.services.ftp_service import FtpStorageError, FtpStorageService
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


def _safe_filename(label: str | None, clip_id: str, fallback_prefix: str = "clip") -> str:
    raw = (label or f"{fallback_prefix}-{clip_id}").strip() or f"{fallback_prefix}-{clip_id}"
    cleaned = re.sub(r"[^\w\-.\s]+", "", raw, flags=re.UNICODE).strip().replace(" ", "-")
    cleaned = cleaned or f"{fallback_prefix}-{clip_id}"
    if not cleaned.lower().endswith(".mp4"):
        cleaned = f"{cleaned}.mp4"
    return cleaned


def _project_subdir(project: Project) -> str:
    slug = re.sub(r"[^\w\-]+", "-", (project.title or str(project.id)).strip()) or str(project.id)
    return slug.strip("-") or str(project.id)


async def _clip_bytes(clip: Clip) -> bytes:
    if clip.local_clip_path:
        path = Path(clip.local_clip_path)
        if path.is_file():
            return await asyncio.to_thread(path.read_bytes)

    if clip.cloudinary_clip_url:
        async with httpx.AsyncClient(follow_redirects=True, timeout=120.0) as client:
            response = await client.get(clip.cloudinary_clip_url)
            response.raise_for_status()
            return response.content

    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Clip file not available")


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


@router.get("/projects/{project_id}/clips/{clip_id}/stream")
async def stream_project_clip(project_id: str, clip_id: str, request: Request, token: str = ""):
    user_id = resolve_user_id_from_token(token, request)
    clip = await Clip.get(clip_id)
    if not clip or clip.project_id != project_id or clip.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Clip not found")

    if clip.cloudinary_clip_url:
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url=clip.cloudinary_clip_url)

    if not clip.local_clip_path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Clip file not available")

    clip_path = Path(clip.local_clip_path)
    if not clip_path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Clip file not found on disk")

    return FileResponse(
        path=str(clip_path),
        media_type="video/mp4",
        filename=f"{clip.label or clip_id}.mp4",
    )


@router.get("/projects/{project_id}/clips/{clip_id}/download")
async def download_project_clip(project_id: str, clip_id: str, request: Request, token: str = ""):
    user_id = resolve_user_id_from_token(token, request)
    clip = await Clip.get(clip_id)
    if not clip or clip.project_id != project_id or clip.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Clip not found")

    if clip.status != ClipStatus.READY:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Clip is not ready for download")

    filename = _safe_filename(clip.label, clip_id)

    if clip.local_clip_path:
        clip_path = Path(clip.local_clip_path)
        if clip_path.is_file():
            return FileResponse(
                path=str(clip_path),
                media_type="video/mp4",
                filename=filename,
                content_disposition_type="attachment",
            )

    if clip.cloudinary_clip_url:
        try:
            data = await _clip_bytes(clip)
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Could not fetch clip for download",
            ) from exc
        return StreamingResponse(
            io.BytesIO(data),
            media_type="video/mp4",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Clip file not available")


@router.get("/projects/{project_id}/clips/download-all")
async def download_all_project_clips(project_id: str, request: Request, token: str = ""):
    user_id = resolve_user_id_from_token(token, request)
    project = await Project.get(project_id)
    if not project or project.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    clips = (
        await Clip.find(
            Clip.project_id == project_id,
            Clip.user_id == user_id,
            Clip.status == ClipStatus.READY,
        )
        .sort("start_time")
        .to_list()
    )
    if not clips:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No ready clips to download")

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".zip")
    tmp_path = Path(tmp.name)
    tmp.close()

    try:
        with zipfile.ZipFile(tmp_path, "w", compression=zipfile.ZIP_STORED) as archive:
            used_names: set[str] = set()
            for index, clip in enumerate(clips, start=1):
                clip_id = str(clip.id)
                base_name = _safe_filename(clip.label or f"Part-{index}", clip_id)
                name = base_name
                if name in used_names:
                    stem = Path(base_name).stem
                    name = f"{stem}-{index}.mp4"
                used_names.add(name)
                try:
                    data = await _clip_bytes(clip)
                except Exception:
                    continue
                archive.writestr(name, data)

            if not archive.namelist():
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Clip files are not available for download",
                )
    except HTTPException:
        tmp_path.unlink(missing_ok=True)
        raise
    except Exception as exc:
        tmp_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not build clips zip",
        ) from exc

    project_slug = re.sub(r"[^\w\-]+", "-", (project.title or "clips").strip()) or "clips"
    zip_name = f"{project_slug}-clips.zip"
    return FileResponse(
        path=str(tmp_path),
        media_type="application/zip",
        filename=zip_name,
        content_disposition_type="attachment",
        background=BackgroundTask(lambda: tmp_path.unlink(missing_ok=True)),
    )


@router.post("/projects/{project_id}/clips/{clip_id}/save-remote")
async def save_project_clip_remote(
    project_id: str,
    clip_id: str,
    user_id: str = Depends(get_current_user_id),
):
    project = await Project.get(project_id)
    if not project or project.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    clip = await Clip.get(clip_id)
    if not clip or clip.project_id != project_id or clip.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Clip not found")

    if clip.status != ClipStatus.READY:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Clip is not ready for download")

    ftp = FtpStorageService()
    if not ftp.is_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="FTP storage is not configured. Set FTP_HOST, FTP_USER, and FTP_PASSWORD.",
        )

    filename = _safe_filename(clip.label, clip_id)
    try:
        data = await _clip_bytes(clip)
    except HTTPException as exc:
        if exc.status_code == status.HTTP_404_NOT_FOUND:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Clip file is not ready yet. Wait for processing to finish, then try again.",
            ) from exc
        raise

    try:
        public_url = await asyncio.to_thread(
            ftp.upload_bytes,
            data,
            filename,
            _project_subdir(project),
        )
    except FtpStorageError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not upload clip to hosting storage",
        ) from exc

    return {
        "saved": True,
        "clip_id": clip_id,
        "filename": filename,
        "url": public_url,
        "storage": "razorhost-ftp",
    }


@router.post("/projects/{project_id}/clips/save-all-remote")
async def save_all_project_clips_remote(
    project_id: str,
    user_id: str = Depends(get_current_user_id),
):
    from app.config import settings

    project = await Project.get(project_id)
    if not project or project.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    ftp = FtpStorageService()
    if not ftp.is_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="FTP storage is not configured. Set FTP_HOST, FTP_USER, and FTP_PASSWORD.",
        )

    clips = (
        await Clip.find(
            Clip.project_id == project_id,
            Clip.user_id == user_id,
            Clip.status == ClipStatus.READY,
        )
        .sort("start_time")
        .to_list()
    )
    if not clips:
        # Helpful detail when clips exist but are still processing / have no files.
        all_clips = await Clip.find(Clip.project_id == project_id, Clip.user_id == user_id).to_list()
        if all_clips:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Clips are still processing. Wait until status is Ready, then save again.",
            )
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No ready clips to save")

    subdir = _project_subdir(project)
    saved: list[dict[str, str]] = []
    errors: list[dict[str, str]] = []
    used_names: set[str] = set()

    for index, clip in enumerate(clips, start=1):
        clip_id = str(clip.id)
        base_name = _safe_filename(clip.label or f"Part-{index}", clip_id)
        name = base_name
        if name in used_names:
            stem = Path(base_name).stem
            name = f"{stem}-{index}.mp4"
        used_names.add(name)

        try:
            data = await _clip_bytes(clip)
            public_url = await asyncio.to_thread(ftp.upload_bytes, data, name, subdir)
            saved.append({"clip_id": clip_id, "filename": name, "url": public_url})
        except Exception as exc:
            errors.append({"clip_id": clip_id, "filename": name, "error": str(exc)})

    if not saved:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not upload any clips to hosting storage",
        )

    folder_url = f"{settings.ftp_public_base_url.rstrip('/')}/{subdir}"
    return {
        "saved": True,
        "storage": "razorhost-ftp",
        "count": len(saved),
        "files": saved,
        "errors": errors,
        "folder_url": folder_url,
    }


@router.get("/projects/{project_id}/clips/{clip_id}/thumbnail")
async def stream_project_clip_thumbnail(project_id: str, clip_id: str, request: Request, token: str = ""):
    user_id = resolve_user_id_from_token(token, request)
    clip = await Clip.get(clip_id)
    if not clip or clip.project_id != project_id or clip.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Clip not found")

    if clip.thumbnail_url:
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url=clip.thumbnail_url)

    if not clip.local_thumbnail_path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Thumbnail not available")

    thumb_path = Path(clip.local_thumbnail_path)
    if not thumb_path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Thumbnail file not found on disk")

    return FileResponse(path=str(thumb_path), media_type="image/jpeg")


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
        try:
            await cloudinary_service.delete_resource(clip.cloudinary_public_id, resource_type="video")
        except Exception:
            pass
        try:
            await cloudinary_service.delete_by_prefix(
                f"projects/{clip.project_id}/clips/{clip_id}",
                resource_type="video",
            )
            await cloudinary_service.delete_by_prefix(
                f"projects/{clip.project_id}/clips/{clip_id}_thumb",
                resource_type="image",
            )
        except Exception:
            pass

    for path_str in (clip.local_clip_path, clip.local_thumbnail_path):
        if path_str:
            path = Path(path_str)
            if path.is_file():
                path.unlink()

    await clip.delete()
    return {"deleted": True, "clip_id": clip_id}
