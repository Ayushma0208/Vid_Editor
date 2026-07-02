from fastapi import APIRouter, BackgroundTasks, Depends, File, UploadFile, status

from app.api.dependencies import get_current_user_id
from app.services.project_upload import create_project_from_upload

router = APIRouter(prefix="/uploads", tags=["uploads"])


@router.post("", status_code=status.HTTP_201_CREATED)
async def upload_video(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    user_id: str = Depends(get_current_user_id),
):
    return await create_project_from_upload(file, user_id, background_tasks)
