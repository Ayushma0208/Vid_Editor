from fastapi import APIRouter

from app.api.v1.auth import router as auth_router
from app.api.v1.assets import router as assets_router
from app.api.v1.captions import router as captions_router
from app.api.v1.clips import router as clips_router
from app.api.v1.projects import router as projects_router
from app.api.v1.publishing import router as publishing_router
from app.api.v1.videos import router as videos_router


api_router = APIRouter()
api_router.include_router(auth_router)
api_router.include_router(projects_router)
api_router.include_router(videos_router)
api_router.include_router(clips_router)
api_router.include_router(captions_router)
api_router.include_router(assets_router)
api_router.include_router(publishing_router)
