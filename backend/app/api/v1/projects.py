import asyncio
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.api.dependencies import get_current_user_id
from app.models.asset import Asset
from app.models.caption import Caption
from app.models.clip import Clip
from app.models.project import Project, ProjectStatus
from app.tasks.download_task import download_video_task


router = APIRouter(prefix="/projects", tags=["projects"])

YOUTUBE_URL_PATTERN = re.compile(
    r"^(https?://)?(www\.)?(youtube\.com/watch\?v=[\w-]+|youtu\.be/[\w-]+)",
    re.IGNORECASE,
)


class CreateProjectRequest(BaseModel):
    yt_url: str


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


async def fetch_yt_metadata(yt_url: str) -> dict[str, Any]:
    process = await asyncio.create_subprocess_exec(
        "yt-dlp",
        "--dump-json",
        yt_url,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await process.communicate()

    if process.returncode != 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Failed to parse YouTube metadata: {stderr.decode().strip()}",
        )

    raw_output = stdout.decode().strip()
    if not raw_output:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="yt-dlp returned empty metadata",
        )

    try:
        return json.loads(raw_output.splitlines()[0])
    except (json.JSONDecodeError, IndexError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Unable to decode yt-dlp metadata",
        ) from exc


@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_project(
    payload: CreateProjectRequest,
    user_id: str = Depends(get_current_user_id),
):
    yt_url = payload.yt_url.strip()
    if not YOUTUBE_URL_PATTERN.match(yt_url):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid YouTube URL. Use youtube.com/watch?v=... or youtu.be/...",
        )

    metadata = await fetch_yt_metadata(yt_url)
    parsed_video_id = parse_video_id(yt_url) or str(metadata.get("id", ""))
    now = datetime.now(timezone.utc)

    project = Project(
        user_id=user_id,
        title=metadata.get("title") or "Untitled video",
        yt_url=yt_url,
        yt_video_id=parsed_video_id,
        status=ProjectStatus.PENDING,
        cloudinary_folder=f"projects/{parsed_video_id or 'unknown'}/",
        duration_seconds=metadata.get("duration"),
        thumbnail_url=metadata.get("thumbnail"),
        metadata=metadata,
        created_at=now,
        updated_at=now,
    )
    await project.insert()

    task = download_video_task.delay(str(project.id), yt_url)
    response = serialize_document(project)
    response["task_id"] = task.id
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

    task = download_video_task.delay(str(project.id), project.yt_url)
    data = serialize_document(project)
    data["task_id"] = task.id
    return data


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
async def stream_video(project_id: str, token: str = ""):
    """Stream the raw video file. Accepts ?token=<jwt> for auth since <video> tags can't send headers."""
    from jose import JWTError, jwt as jose_jwt
    from app.config import settings as app_settings

    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token required")

    try:
        payload = jose_jwt.decode(token, app_settings.jwt_secret_key, algorithms=[app_settings.jwt_algorithm])
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    if payload.get("type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token type")

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

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
