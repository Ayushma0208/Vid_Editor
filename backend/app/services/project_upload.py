import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import BackgroundTasks, HTTPException, UploadFile, status

from app.config import settings
from app.models.project import Project, ProjectStatus
from app.tasks.upload_task import _run_upload_pipeline_background
from app.utils.ffmpeg_utils import ffmpeg_available, ffmpeg_missing_message

ALLOWED_UPLOAD_CONTENT_TYPES = {
    "video/mp4",
    "video/webm",
    "video/quicktime",
    "video/x-msvideo",
    "video/x-matroska",
    "application/octet-stream",
}
ALLOWED_UPLOAD_EXTENSIONS = {".mp4", ".webm", ".mov", ".avi", ".mkv", ".m4v"}


def validate_video_upload(file: UploadFile) -> str:
    if not file.filename:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Video file is required")

    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_UPLOAD_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Unsupported format. Use MP4, MOV, WebM, AVI, or MKV.",
        )

    content_type = (file.content_type or "").lower()
    if content_type and content_type not in ALLOWED_UPLOAD_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unsupported content type: {content_type}",
        )
    return ext


async def save_uploaded_video(file: UploadFile, dest_path: Path) -> int:
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    total = 0
    try:
        with dest_path.open("wb") as out:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > settings.max_upload_size_bytes:
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail="Video is too large. Maximum upload size is 5 GB.",
                    )
                out.write(chunk)
    except HTTPException:
        if dest_path.exists():
            dest_path.unlink()
        raise
    except Exception as exc:
        if dest_path.exists():
            dest_path.unlink()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Could not save uploaded video: {exc}",
        ) from exc

    if total == 0:
        if dest_path.exists():
            dest_path.unlink()
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Uploaded file is empty")
    return total


def serialize_document(doc: Any) -> dict[str, Any]:
    from fastapi.encoders import jsonable_encoder

    data = jsonable_encoder(doc.model_dump(by_alias=True))
    if "_id" in data:
        data["id"] = str(data.pop("_id"))
    return data


async def create_project_from_upload(
    file: UploadFile | list[UploadFile],
    user_id: str,
    background_tasks: BackgroundTasks,
) -> dict[str, Any]:
    if not ffmpeg_available():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=ffmpeg_missing_message(),
        )

    files = [item for item in (file if isinstance(file, list) else [file]) if item is not None]
    files = [item for item in files if item.filename]
    if not files:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Video file is required")

    upload_dir = Path(settings.temp_dir) / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)

    saved_paths: list[Path] = []
    filenames: list[str] = []
    total = 0
    try:
        for index, item in enumerate(files):
            ext = validate_video_upload(item)
            safe_name = re.sub(r"[^a-zA-Z0-9._-]+", "-", Path(item.filename).stem).strip("-") or "video"
            temp_path = upload_dir / f"{user_id}-{index}-{safe_name}{ext}"
            total += await save_uploaded_video(item, temp_path)
            saved_paths.append(temp_path)
            filenames.append(str(item.filename))
    except Exception:
        for path in saved_paths:
            if path.exists():
                path.unlink()
        raise

    now = datetime.now(timezone.utc)
    title = Path(filenames[0]).stem or "Uploaded video"
    project = Project(
        user_id=user_id,
        title=title,
        yt_url=f"upload://{Path(filenames[0]).stem}",
        yt_video_id="pending",
        status=ProjectStatus.PENDING,
        cloudinary_folder="projects/uploads/",
        metadata={
            "source": "upload",
            "original_filename": filenames[0],
            "original_filenames": filenames,
            "upload_size_bytes": total,
            "upload_file_count": len(saved_paths),
        },
        created_at=now,
        updated_at=now,
    )
    await project.insert()
    project.yt_video_id = f"upload-{project.id}"
    await project.save()

    from app.services.pipeline_runtime import claim_pipeline

    claim_pipeline(str(project.id))
    background_tasks.add_task(
        _run_upload_pipeline_background,
        str(project.id),
        saved_paths[0],
        saved_paths[1:],
    )

    response = serialize_document(project)
    response["execution_mode"] = "local-background"
    response["segment_seconds"] = settings.default_clip_duration_seconds
    response["message"] = (
        "Videos uploaded. Sorting by quality and sending each file to its host…"
    )
    return response
