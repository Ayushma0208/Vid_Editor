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
from app.models.project import Project, ProjectStatus, SummaryStatus
from app.services.project_upload import (
    create_project_from_upload,
    save_uploaded_video,
    validate_video_upload,
)
from app.services.quality_host_routing import TARGET_QUALITY_KEYS, build_quality_distribute_plan, quality_key
from app.services.ytdlp_service import YTDLPService
from app.tasks.clip_task import (
    _resolve_clip_source_path,
    CLOUDINARY_SYNC_KEY,
    trigger_auto_generate_clips,
    trigger_upload_project_clips_to_cloudinary,
)
from app.services.cloudinary_service import CloudinaryService
from app.tasks.download_task import (
    _run_download_pipeline,
    _run_refetch_pipeline,
    _set_project_error,
    download_video_task,
)
from app.tasks.quality_distribute_task import trigger_distribute_project_qualities
from app.tasks.summary_task import trigger_project_summary
from app.tasks.upload_task import attach_quality_file, is_upload_project, retry_upload_processing
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


class UpdateSummaryRequest(BaseModel):
    summary: str


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
    from app.services.pipeline_runtime import release_pipeline

    project = await Project.get(project_id)
    if not project:
        release_pipeline(project_id)
        return
    try:
        await _run_download_pipeline(project_id, video_url)
    except Exception as exc:
        await _set_project_error(project, str(exc))
    finally:
        release_pipeline(project_id)


async def _run_refetch_pipeline_background(project_id: str, video_url: str) -> None:
    project = await Project.get(project_id)
    if not project:
        return
    try:
        await _run_refetch_pipeline(project_id, video_url)
    except Exception as exc:
        await _set_project_error(project, str(exc))


async def trigger_refetch_source(project_id: str, video_url: str) -> dict[str, Any]:
    from app.services.pipeline_runtime import spawn_background

    spawn_background(_run_refetch_pipeline_background(project_id, video_url))
    return {"task_id": None, "execution_mode": "local-background"}


async def trigger_download(project_id: str, video_url: str) -> dict[str, Any]:
    from app.services.pipeline_runtime import claim_pipeline, release_pipeline

    try:
        task = download_video_task.delay(project_id, video_url)
        inspector = await asyncio.to_thread(download_video_task.app.control.inspect, timeout=0.5)
        ping = await asyncio.to_thread(inspector.ping) if inspector else None
        if ping:
            return {"task_id": task.id, "execution_mode": "celery"}
    except Exception:
        pass

    claim_pipeline(project_id)
    try:
        from app.services.pipeline_runtime import spawn_background

        spawn_background(_run_download_pipeline_background(project_id, video_url))
    except Exception:
        release_pipeline(project_id)
        raise
    return {"task_id": None, "execution_mode": "local-background"}


@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_project(
    payload: CreateProjectRequest,
    user_id: str = Depends(get_current_user_id),
):
    raw_url = payload.yt_url.strip()
    if not raw_url:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="A video URL is required",
        )

    # YouTube URLs are normalized; other yt-dlp-compatible https URLs are accepted as-is.
    if YOUTUBE_URL_PATTERN.match(raw_url):
        yt_url = normalize_youtube_url(raw_url)
    elif re.match(r"^https?://", raw_url, re.IGNORECASE):
        yt_url = raw_url
    else:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid URL. Use an https video URL that yt-dlp can process (rights-ok sources only).",
        )

    metadata: dict[str, Any] = {}
    metadata_error: str | None = None
    try:
        metadata = await YTDLPService().get_metadata(yt_url)
    except Exception as exc:
        metadata_error = str(exc)

    parsed_video_id = parse_video_id(yt_url) or str(metadata.get("id", "")) or "source"
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
        quality_assets={},
        clip_source_quality=settings.clip_source_quality or "720",
        metadata={
            **{k: v for k, v in (metadata or {}).items() if k != "formats"},
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
    try:
        from app.services.pipeline_runtime import fail_dead_upload_if_source_missing, resume_stale_project

        recovered = []
        for project in projects:
            if project.status in (ProjectStatus.PENDING, ProjectStatus.DOWNLOADING):
                project = await fail_dead_upload_if_source_missing(project)
                await resume_stale_project(project)
            recovered.append(project)
        projects = recovered
    except Exception:
        pass
    return [serialize_document(project) for project in projects]


@router.get("/{project_id}")
async def get_project(project_id: str, user_id: str = Depends(get_current_user_id)):
    try:
        project = await Project.get(project_id)
    except Exception:
        project = None
    if not project or project.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    pipeline_running = False
    try:
        from app.services.pipeline_runtime import (
            fail_dead_upload_if_source_missing,
            pipeline_claimed,
            resume_stale_project,
        )

        project = await fail_dead_upload_if_source_missing(project)
        await resume_stale_project(project)
        project = await Project.get(project_id) or project
        pipeline_running = pipeline_claimed(project_id)
    except Exception:
        pass

    data = serialize_document(project)
    data["download_status"] = project.status
    data["pipeline_running"] = pipeline_running
    data["processing_step"] = (project.metadata or {}).get("processing_step")
    local_path = Path(project.local_video_path) if project.local_video_path else None
    from app.tasks.upload_task import is_upload_project

    usable = None
    try:
        from app.tasks.clip_task import _resolve_clip_source_path

        usable = _resolve_clip_source_path(project)
    except Exception:
        usable = None
    data["source_file_available"] = bool(usable or (local_path and local_path.is_file()))
    data["is_upload"] = is_upload_project(project)
    data["has_cloudinary_raw"] = bool(project.cloudinary_raw_url)
    # Only after processing finished — during downloading/pending the file isn't ready yet.
    finished = project.status in (ProjectStatus.READY, ProjectStatus.ERROR)
    data["needs_reupload"] = bool(
        finished
        and is_upload_project(project)
        and not data["source_file_available"]
        and not project.cloudinary_raw_url
    )
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

    if not is_upload_project(project):
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

    if project.status not in (
        ProjectStatus.PENDING,
        ProjectStatus.DOWNLOADING,
        ProjectStatus.ERROR,
    ):
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


@router.post("/{project_id}/refetch-source")
async def refetch_source(project_id: str, user_id: str = Depends(get_current_user_id)):
    """Re-download / restore source and re-process clips when local temp files were lost."""
    project = await Project.get(project_id)
    if not project or project.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    from app.tasks.clip_task import _resolve_clip_source_path, run_clip_processing
    from app.tasks.upload_task import is_upload_project, restore_upload_source_from_cloudinary

    # Manual uploads must never go through yt-dlp (yt_url is upload://...).
    if is_upload_project(project):
        usable_source = _resolve_clip_source_path(project)
        if usable_source:
            clips = await Clip.find(Clip.project_id == project_id, Clip.user_id == user_id).to_list()
            missing_clips = [
                c
                for c in clips
                if not (c.local_clip_path and Path(c.local_clip_path).is_file())
                and not c.cloudinary_clip_url
            ]
            if not missing_clips:
                return {
                    "project_id": project_id,
                    "message": "Source video and clip files are already available.",
                    "source_file_available": True,
                }
            for clip in missing_clips:
                await run_clip_processing(project_id, str(clip.id))
            return {
                "project_id": project_id,
                "message": f"Re-processed {len(missing_clips)} clip(s) from the existing source video.",
                "reprocessed_clips": len(missing_clips),
                "execution_mode": "inline",
            }

        if project.cloudinary_raw_url:
            if project.status == ProjectStatus.DOWNLOADING:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Source video is already being restored. Please wait.",
                )

            async def _restore_upload_bg() -> None:
                try:
                    await restore_upload_source_from_cloudinary(project)
                except Exception as exc:
                    fresh = await Project.get(project_id)
                    if fresh:
                        meta = dict(fresh.metadata or {})
                        meta["error_message"] = str(exc)
                        fresh.metadata = meta
                        fresh.status = ProjectStatus.ERROR
                        await fresh.save()

            asyncio.create_task(_restore_upload_bg())
            return {
                "project_id": project_id,
                "message": "Restoring uploaded video from Cloudinary and rebuilding clips…",
                "execution_mode": "local-background",
            }

        meta = dict(project.metadata or {})
        if meta.get("error_message") and "upload" in str(meta.get("error_message")).lower():
            meta.pop("error_message", None)
            project.metadata = meta
            if project.status == ProjectStatus.ERROR:
                project.status = ProjectStatus.READY
            await project.save()

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "This is a manual upload — the original file is gone from the server "
                "and there is no Cloudinary backup. Please upload the video again."
            ),
        )

    if not project.yt_url:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This project has no YouTube URL to re-download from.",
        )

    usable_source = _resolve_clip_source_path(project)
    if usable_source:
        clips = await Clip.find(Clip.project_id == project_id, Clip.user_id == user_id).to_list()
        missing_clips = [
            c
            for c in clips
            if not (c.local_clip_path and Path(c.local_clip_path).is_file()) and not c.cloudinary_clip_url
        ]
        if not missing_clips:
            return {
                "project_id": project_id,
                "message": "Source video and clip files are already available.",
                "source_file_available": True,
            }

        for clip in missing_clips:
            await run_clip_processing(project_id, str(clip.id))

        return {
            "project_id": project_id,
            "message": f"Re-processed {len(missing_clips)} clip(s) from the existing source video.",
            "reprocessed_clips": len(missing_clips),
            "execution_mode": "inline",
        }

    if project.status == ProjectStatus.DOWNLOADING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Source video is already being re-downloaded. Please wait.",
        )

    trigger = await trigger_refetch_source(project_id, project.yt_url)
    return {
        "project_id": project_id,
        "message": "Re-downloading source video and re-processing clips. This may take a few minutes.",
        "task_id": trigger.get("task_id"),
        "execution_mode": trigger.get("execution_mode"),
    }


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

    clip_key = quality_key(project.clip_source_quality or settings.clip_source_quality or "720")
    clip_source = _resolve_clip_source_path(project)
    if not clip_source and not project.cloudinary_raw_url:
        from app.tasks.upload_task import is_upload_project

        detail = (
            "No local video available for clip generation. "
            + (
                "Please upload the video again."
                if is_upload_project(project)
                else f"Need {clip_key}p (or another ready quality), or use Refetch source."
            )
        )
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)

    if not segment_seconds or segment_seconds < 1:
        segment_seconds = settings.default_clip_duration_seconds

    if (project.metadata or {}).get("auto_clip_warning"):
        meta = dict(project.metadata or {})
        meta.pop("auto_clip_warning", None)
        project.metadata = meta
        project.updated_at = datetime.now(timezone.utc)
        await project.save()

    trigger = await trigger_auto_generate_clips(project_id, segment_seconds)
    return {
        "project_id": project_id,
        "task_id": trigger.get("task_id"),
        "execution_mode": trigger.get("execution_mode"),
        "segment_seconds": segment_seconds,
        "clip_source_quality": clip_key,
        "message": f"Generating {segment_seconds}-second clips",
    }


@router.get("/{project_id}/clips/upload-cloudinary")
async def get_cloudinary_clip_upload_status(
    project_id: str,
    user_id: str = Depends(get_current_user_id),
):
    project = await Project.get(project_id)
    if not project or project.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    clips = await Clip.find(Clip.project_id == project_id, Clip.user_id == user_id).to_list()
    with_url = sum(1 for c in clips if c.cloudinary_clip_url)
    sync = dict((project.metadata or {}).get(CLOUDINARY_SYNC_KEY) or {})
    return {
        "project_id": project_id,
        "cloudinary_configured": CloudinaryService().is_configured(),
        "total": len(clips),
        "uploaded": with_url,
        "missing": max(0, len(clips) - with_url),
        "status": sync.get("status") or ("done" if with_url == len(clips) else "idle"),
        "failed": int(sync.get("failed") or 0),
        "error": sync.get("error"),
        "processing_step": (project.metadata or {}).get("processing_step"),
    }


@router.post("/{project_id}/clips/upload-cloudinary")
async def upload_project_clips_to_cloudinary(
    project_id: str,
    user_id: str = Depends(get_current_user_id),
):
    project = await Project.get(project_id)
    if not project or project.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    if not CloudinaryService().is_configured():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cloudinary is not configured. Set CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, and CLOUDINARY_API_SECRET.",
        )
    clips = await Clip.find(Clip.project_id == project_id, Clip.user_id == user_id).to_list()
    missing = [c for c in clips if not c.cloudinary_clip_url]
    sync = dict((project.metadata or {}).get(CLOUDINARY_SYNC_KEY) or {})
    if not missing:
        return {
            "project_id": project_id,
            "status": "done",
            "total": len(clips),
            "missing": 0,
            "message": "All clips already have Cloudinary URLs.",
        }
    if sync.get("status") == "running":
        return {
            "project_id": project_id,
            "status": "running",
            "total": len(clips),
            "missing": len(missing),
            "message": "Cloudinary clip upload is already running.",
        }
    meta = dict(project.metadata or {})
    meta[CLOUDINARY_SYNC_KEY] = {
        "status": "running",
        "total": len(clips),
        "missing": len(missing),
        "uploaded": 0,
        "failed": 0,
        "error": None,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    project.metadata = meta
    project.updated_at = datetime.now(timezone.utc)
    await project.save()
    trigger = await trigger_upload_project_clips_to_cloudinary(project_id)
    return {
        "project_id": project_id,
        "status": "running",
        "total": len(clips),
        "missing": len(missing),
        "task_id": trigger.get("task_id"),
        "execution_mode": trigger.get("execution_mode"),
        "message": f"Uploading {len(missing)} clip(s) to Cloudinary for Instagram.",
    }


@router.get("/{project_id}/qualities")
async def get_project_qualities(project_id: str, user_id: str = Depends(get_current_user_id)):
    project = await Project.get(project_id)
    if not project or project.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    plan = build_quality_distribute_plan(project.quality_assets)
    return {
        "project_id": project_id,
        "clip_source_quality": project.clip_source_quality or settings.clip_source_quality,
        "clips_expire_at": project.clips_expire_at.isoformat() if project.clips_expire_at else None,
        **plan,
    }


@router.post("/{project_id}/qualities/{quality}")
async def upload_project_quality(
    project_id: str,
    quality: str,
    file: UploadFile = File(...),
    user_id: str = Depends(get_current_user_id),
):
    project = await Project.get(project_id)
    if not project or project.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    key = quality_key(quality)
    if key not in TARGET_QUALITY_KEYS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unsupported quality. Use one of: {', '.join(q + 'p' for q in TARGET_QUALITY_KEYS)}",
        )

    if not ffmpeg_available():
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=ffmpeg_missing_message())

    ext = validate_video_upload(file)
    staging_dir = Path(settings.temp_dir) / "uploads" / project_id
    staging_dir.mkdir(parents=True, exist_ok=True)
    staging_path = staging_dir / f"{key}{ext}"
    await save_uploaded_video(file, staging_path)

    try:
        result = await attach_quality_file(project_id, key, staging_path)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    finally:
        try:
            if staging_path.exists():
                staging_path.unlink()
        except OSError:
            pass

    fresh = await Project.get(project_id)
    plan = build_quality_distribute_plan(fresh.quality_assets if fresh else project.quality_assets)
    return {
        **result,
        **plan,
    }


class DistributeQualitiesBody(BaseModel):
    qualities: list[str] | None = None
    only_failed: bool = True


@router.post("/{project_id}/distribute/qualities")
async def distribute_project_qualities_endpoint(
    project_id: str,
    body: DistributeQualitiesBody | None = None,
    user_id: str = Depends(get_current_user_id),
):
    project = await Project.get(project_id)
    if not project or project.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    payload = body or DistributeQualitiesBody()
    trigger = await trigger_distribute_project_qualities(
        project_id,
        qualities=payload.qualities,
        only_failed=payload.only_failed,
    )
    return {
        "project_id": project_id,
        "task_id": trigger.get("task_id"),
        "execution_mode": trigger.get("execution_mode"),
        "only_failed": payload.only_failed,
        "message": "Queued full-movie quality uploads to hosts",
    }


@router.post("/{project_id}/generate-summary")
async def generate_summary(project_id: str, user_id: str = Depends(get_current_user_id)):
    project = await Project.get(project_id)
    if not project or project.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    local_path = Path(project.local_video_path) if project.local_video_path else None
    has_video = bool(local_path and local_path.is_file())
    has_source_text = bool((project.metadata or {}).get("description") or project.title)
    if project.status != ProjectStatus.READY and not has_video and not has_source_text:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Project video is not ready for summary generation",
        )

    trigger = await trigger_project_summary(project_id)
    return {
        "project_id": project_id,
        "task_id": trigger.get("task_id"),
        "execution_mode": trigger.get("execution_mode"),
        "summary_status": trigger.get("summary_status"),
        "message": "Generating full-video summary for Instagram captions",
    }


@router.patch("/{project_id}/summary")
async def update_summary(
    project_id: str,
    payload: UpdateSummaryRequest,
    user_id: str = Depends(get_current_user_id),
):
    project = await Project.get(project_id)
    if not project or project.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    summary = payload.summary.strip()
    if not summary:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Summary cannot be empty")
    if len(summary) > 2200:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Summary must be at most 2200 characters",
        )

    project.summary = summary
    project.summary_status = SummaryStatus.READY
    project.summary_error = None
    project.updated_at = datetime.now(timezone.utc)
    await project.save()
    return serialize_document(project)


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
