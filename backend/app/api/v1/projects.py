import asyncio
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Request, UploadFile, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.api.dependencies import get_current_user_id, resolve_user_id_from_token
from app.config import settings
from app.models.asset import Asset
from app.models.caption import Caption
from app.models.clip import Clip, ClipStatus, ClipType
from app.models.project import Project, ProjectStatus
from app.services.ytdlp_service import YTDLPService
from app.tasks.clip_task import trigger_auto_generate_clips
from app.tasks.download_task import _run_download_pipeline, _set_project_error, download_video_task
from app.services.project_upload import create_project_from_upload
from app.tasks.upload_task import retry_upload_processing
from app.utils.ffmpeg_utils import ffmpeg_available, ffmpeg_missing_message, get_ffmpeg_path, get_ffprobe_path


router = APIRouter(prefix="/projects", tags=["projects"])

YOUTUBE_URL_PATTERN = re.compile(
    r"^(https?://)?(www\.)?(youtube\.com/watch\?v=[\w-]+|youtu\.be/[\w-]+)",
    re.IGNORECASE,
)


class CreateProjectRequest(BaseModel):
    yt_url: str


class SeedDummyProjectRequest(BaseModel):
    file_name: str


def serialize_document(doc: Any) -> dict[str, Any]:
    data = jsonable_encoder(doc.model_dump(by_alias=True))
    if "_id" in data:
        data["id"] = str(data.pop("_id"))
    return data


def parse_video_id(yt_url: str) -> str:
    short_pattern = re.search(r"youtu\.be/([\w-]+)", yt_url)
    if short_pattern:
        return short_pattern.group(1)
    long_pattern = re.search(r"[?&]v=([\w-]+)", yt_url)
    if long_pattern:
        return long_pattern.group(1)
    return ""


def normalize_youtube_url(raw_url: str) -> str:
    parsed = urlparse(raw_url)
    host = parsed.netloc.lower()
    query = parse_qs(parsed.query)

    if "youtu.be" in host:
        video_id = parsed.path.strip("/").split("/")[0]
        return f"https://youtu.be/{video_id}" if video_id else raw_url

    if "youtube.com" in host:
        video_id = query.get("v", [""])[0]
        if video_id:
            return f"https://www.youtube.com/watch?v={video_id}"

    return raw_url


async def probe_local_video_duration(video_path: Path) -> float | None:
    process = await asyncio.create_subprocess_exec(
        get_ffprobe_path() or "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(video_path),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, _ = await process.communicate()
    if process.returncode != 0:
        return None
    try:
        return float(stdout.decode().strip())
    except ValueError:
        return None


async def generate_local_thumbnail(video_path: Path, output_path: Path) -> bool:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    process = await asyncio.create_subprocess_exec(
        get_ffmpeg_path() or "ffmpeg",
        "-y",
        "-ss",
        "2",
        "-i",
        str(video_path),
        "-frames:v",
        "1",
        str(output_path),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    await process.communicate()
    return process.returncode == 0 and output_path.exists()


async def _run_download_pipeline_background(project_id: str, video_url: str) -> None:
    project = await Project.get(project_id)
    if not project:
        return
    try:
        await _run_download_pipeline(project_id, video_url)
    except Exception as exc:
        await _set_project_error(project, str(exc))


async def trigger_download(project_id: str, video_url: str) -> dict[str, Any]:
    try:
        task = download_video_task.delay(project_id, video_url)
        inspector = await asyncio.to_thread(download_video_task.app.control.inspect, timeout=0.5)
        ping = await asyncio.to_thread(inspector.ping) if inspector else None
        if ping:
            return {"task_id": task.id, "execution_mode": "celery"}
    except Exception:
        pass

    asyncio.create_task(_run_download_pipeline_background(project_id, video_url))
    return {"task_id": None, "execution_mode": "local-background"}


@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_project(
    payload: CreateProjectRequest,
    user_id: str = Depends(get_current_user_id),
):
    yt_url = normalize_youtube_url(payload.yt_url.strip())
    if not YOUTUBE_URL_PATTERN.match(yt_url):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid YouTube URL. Use youtube.com/watch?v=... or youtu.be/...",
        )

    metadata: dict[str, Any] = {}
    metadata_error: str | None = None
    try:
        metadata = await YTDLPService().get_metadata(yt_url)
    except Exception as exc:
        metadata_error = str(exc)

    parsed_video_id = parse_video_id(yt_url) or str(metadata.get("id", ""))
    now = datetime.now(timezone.utc)

    title = metadata.get("title") if metadata else None
    if metadata_error and not title:
        title = "Untitled video"

    project = Project(
        user_id=user_id,
        title=title or "Untitled video",
        yt_url=yt_url,
        yt_video_id=parsed_video_id,
        status=ProjectStatus.PENDING,
        cloudinary_folder=f"projects/{parsed_video_id or 'unknown'}/",
        duration_seconds=metadata.get("duration"),
        thumbnail_url=metadata.get("thumbnail"),
        metadata={
            **metadata,
            **({"metadata_fetch_error": metadata_error} if metadata_error else {}),
        },
        created_at=now,
        updated_at=now,
    )
    await project.insert()

    response = serialize_document(project)
    trigger = await trigger_download(str(project.id), yt_url)
    response["task_id"] = trigger["task_id"]
    response["execution_mode"] = trigger["execution_mode"]
    return response


@router.post("/upload", status_code=status.HTTP_201_CREATED, include_in_schema=False)
async def upload_project_legacy(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    user_id: str = Depends(get_current_user_id),
):
    return await create_project_from_upload(file, user_id, background_tasks)


@router.post("/seed-dummy", status_code=status.HTTP_201_CREATED)
async def seed_dummy_project(
    payload: SeedDummyProjectRequest,
    user_id: str = Depends(get_current_user_id),
):
    raw_file_name = payload.file_name.strip()
    if not raw_file_name:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="file_name is required")

    now = datetime.now(timezone.utc)
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", raw_file_name.lower()).strip("-") or "dummy-project"
    local_video_path = Path(raw_file_name)
    if not local_video_path.is_absolute():
        local_video_path = Path.cwd() / raw_file_name
    if not local_video_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Seed video not found: {raw_file_name}")

    duration = await probe_local_video_duration(local_video_path)
    thumbnail_path = Path(settings.temp_dir) / "seed" / slug / "thumbnail.jpg"
    thumbnail_created = await generate_local_thumbnail(local_video_path, thumbnail_path)

    project = Project(
        user_id=user_id,
        title=f"Seed: {raw_file_name}",
        yt_url=f"local://{raw_file_name}",
        yt_video_id=f"seed-{slug[:30]}",
        status=ProjectStatus.READY,
        cloudinary_folder=f"projects/seed/{slug}/",
        local_video_path=str(local_video_path),
        duration_seconds=duration,
        thumbnail_url=None,
        metadata={
            "seed_file_name": raw_file_name,
            "seeded": True,
            "local_thumbnail_path": str(thumbnail_path) if thumbnail_created else None,
        },
        created_at=now,
        updated_at=now,
    )
    await project.insert()

    default_clips = [
        {
            "label": "Intro segment",
            "start_time": 0.0,
            "end_time": 30.0,
            "clip_type": ClipType.THIRTY_SECONDS,
        },
        {
            "label": "Main explanation",
            "start_time": 30.0,
            "end_time": 60.0,
            "clip_type": ClipType.THIRTY_SECONDS,
        },
    ]

    for clip_data in default_clips:
        clip = Clip(
            project_id=str(project.id),
            user_id=user_id,
            label=clip_data["label"],
            start_time=clip_data["start_time"],
            end_time=clip_data["end_time"],
            duration=clip_data["end_time"] - clip_data["start_time"],
            clip_type=clip_data["clip_type"],
            status=ClipStatus.READY,
            created_at=now,
        )
        await clip.insert()

    response = serialize_document(project)
    response["thumbnail_url"] = f"/api/v1/projects/{response['id']}/thumbnail"
    response["seeded"] = True
    response["seed_file_name"] = raw_file_name
    return response


@router.get("/")
async def list_projects(user_id: str = Depends(get_current_user_id)):
    projects = await Project.find(Project.user_id == user_id).sort("-created_at").to_list()
    return [serialize_document(project) for project in projects]


@router.get("/{project_id}")
async def get_project(project_id: str, user_id: str = Depends(get_current_user_id)):
    project = await Project.get(project_id)
    if not project or project.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    data = serialize_document(project)
    data["download_status"] = project.status
    return data


@router.post("/{project_id}/retry-processing")
async def retry_processing(
    project_id: str,
    background_tasks: BackgroundTasks,
    user_id: str = Depends(get_current_user_id),
):
    project = await Project.get(project_id)
    if not project or project.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    metadata = project.metadata or {}
    if metadata.get("source") != "upload":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Retry processing is only available for uploaded videos.",
        )

    if not ffmpeg_available():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=ffmpeg_missing_message(),
        )

    try:
        await retry_upload_processing(project, background_tasks)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc

    data = serialize_document(project)
    data["message"] = "Processing restarted."
    return data


@router.post("/{project_id}/retry-download")
async def retry_download(project_id: str, user_id: str = Depends(get_current_user_id)):
    project = await Project.get(project_id)
    if not project or project.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    if project.status not in (ProjectStatus.PENDING, ProjectStatus.ERROR):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot retry download — project status is '{project.status.value}'",
        )

    project.status = ProjectStatus.PENDING
    project.updated_at = datetime.now(timezone.utc)
    metadata = project.metadata or {}
    metadata.pop("error_message", None)
    project.metadata = metadata
    await project.save()

    data = serialize_document(project)
    trigger = await trigger_download(str(project.id), project.yt_url)
    data["task_id"] = trigger["task_id"]
    data["execution_mode"] = trigger["execution_mode"]
    return data


@router.post("/{project_id}/generate-clips")
async def generate_clips(
    project_id: str,
    user_id: str = Depends(get_current_user_id),
    segment_seconds: int | None = None,
):
    project = await Project.get(project_id)
    if not project or project.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    if project.status != ProjectStatus.READY:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Project must be ready before generating clips",
        )

    local_path = Path(project.local_video_path) if project.local_video_path else None
    if not local_path or not local_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Downloaded video file is not available on the server",
        )

    if not segment_seconds or segment_seconds < 1:
        segment_seconds = settings.default_clip_duration_seconds

    trigger = await trigger_auto_generate_clips(project_id, segment_seconds)
    return {
        "project_id": project_id,
        "task_id": trigger.get("task_id"),
        "execution_mode": trigger.get("execution_mode"),
        "segment_seconds": segment_seconds,
        "message": f"Generating {segment_seconds}-second clips for the full video",
    }


@router.delete("/{project_id}")
async def delete_project(project_id: str, user_id: str = Depends(get_current_user_id)):
    project = await Project.get(project_id)
    if not project or project.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    await Clip.find(Clip.project_id == project_id).delete()
    await Caption.find(Caption.project_id == project_id).delete()
    await Asset.find(Asset.project_id == project_id).delete()
    await project.delete()

    return {"deleted": True, "project_id": project_id}


@router.get("/{project_id}/stream")
async def stream_video(project_id: str, request: Request, token: str = ""):
    """Stream the raw video file. Accepts ?token=<jwt> or Authorization: Bearer."""
    user_id = resolve_user_id_from_token(token, request)

    project = await Project.get(project_id)
    if not project or project.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    if not project.local_video_path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Video file not available")

    video_path = Path(project.local_video_path)
    if not video_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Video file not found on disk")

    return FileResponse(
        path=str(video_path),
        media_type="video/mp4",
        filename=f"{project.title or 'video'}.mp4",
    )


@router.get("/{project_id}/thumbnail")
async def stream_thumbnail(project_id: str, request: Request, token: str = ""):
    user_id = resolve_user_id_from_token(token, request)

    project = await Project.get(project_id)
    if not project or project.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    metadata = project.metadata or {}
    thumb_path = metadata.get("local_thumbnail_path")
    if not thumb_path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Thumbnail not available")
    thumbnail = Path(thumb_path)
    if not thumbnail.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Thumbnail file not found")

    return FileResponse(path=str(thumbnail), media_type="image/jpeg", filename=f"{project.title or 'thumbnail'}.jpg")
