from fastapi import APIRouter


router = APIRouter(prefix="/videos", tags=["videos"])


@router.post("/download")
async def download_video():
    return {"message": "Queue YouTube download via yt-dlp"}
