from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, UploadFile, status

from app.api.dependencies import get_current_user_id
from app.services.project_upload import create_project_from_upload

router = APIRouter(prefix="/uploads", tags=["uploads"])


@router.post("", status_code=status.HTTP_201_CREATED)
async def upload_video(
    request: Request,
    background_tasks: BackgroundTasks,
    user_id: str = Depends(get_current_user_id),
):
    form = await request.form()
    uploads: list[UploadFile] = []
    seen: set[int] = set()
    for key in ("files", "file"):
        for item in form.getlist(key):
            filename = getattr(item, "filename", None)
            if not filename or not hasattr(item, "read"):
                continue
            marker = id(item)
            if marker in seen:
                continue
            seen.add(marker)
            uploads.append(item)  # type: ignore[arg-type]
    if not uploads:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Video file is required",
        )
    return await create_project_from_upload(uploads, user_id, background_tasks)
