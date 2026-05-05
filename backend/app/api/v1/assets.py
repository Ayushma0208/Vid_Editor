import asyncio
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel

from app.api.dependencies import get_current_user_id
from app.models.asset import Asset, AssetSource, AssetType
from app.models.project import Project
from app.services.pexels_service import PexelsService
from app.services.pixabay_service import PixabayService


router = APIRouter(tags=["assets"])


class SearchType(str, Enum):
    IMAGE = "image"
    VIDEO = "video"
    ALL = "all"


class SearchSource(str, Enum):
    PEXELS = "pexels"
    PIXABAY = "pixabay"
    ALL = "all"


class SaveAssetRequest(BaseModel):
    source_id: str
    source: AssetSource
    asset_type: AssetType
    url: str
    thumbnail_url: str | None = None
    query_used: str | None = None
    photographer: str | None = None


def serialize_document(doc: Any) -> dict[str, Any]:
    return jsonable_encoder(doc.model_dump(by_alias=True))


def interleave_by_source(pexels_items: list[dict[str, Any]], pixabay_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    max_len = max(len(pexels_items), len(pixabay_items))
    for index in range(max_len):
        if index < len(pexels_items):
            merged.append(pexels_items[index])
        if index < len(pixabay_items):
            merged.append(pixabay_items[index])
    return merged


@router.get("/assets/search")
async def search_assets(
    q: str = Query(..., min_length=1),
    type: SearchType = Query(default=SearchType.IMAGE),
    source: SearchSource = Query(default=SearchSource.ALL),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=80),
):
    pexels_service = PexelsService()
    pixabay_service = PixabayService()

    async def search_pexels() -> list[dict[str, Any]]:
        if type == SearchType.VIDEO:
            return await pexels_service.search_videos(q, page, per_page)
        if type == SearchType.ALL:
            photos, videos = await asyncio.gather(
                pexels_service.search_photos(q, page, per_page),
                pexels_service.search_videos(q, page, per_page),
            )
            return photos + videos
        return await pexels_service.search_photos(q, page, per_page)

    async def search_pixabay() -> list[dict[str, Any]]:
        if type == SearchType.VIDEO:
            return await pixabay_service.search_videos(q, page, per_page)
        if type == SearchType.ALL:
            images, videos = await asyncio.gather(
                pixabay_service.search_images(q, page, per_page),
                pixabay_service.search_videos(q, page, per_page),
            )
            return images + videos
        return await pixabay_service.search_images(q, page, per_page)

    if source == SearchSource.ALL:
        pexels_results, pixabay_results = await asyncio.gather(search_pexels(), search_pixabay())
        merged_results = interleave_by_source(pexels_results, pixabay_results)
    elif source == SearchSource.PEXELS:
        merged_results = await search_pexels()
    else:
        merged_results = await search_pixabay()

    return {
        "results": merged_results,
        "total": len(merged_results),
        "page": page,
        "per_page": per_page,
    }


@router.post("/projects/{project_id}/assets", status_code=status.HTTP_201_CREATED)
async def save_project_asset(
    project_id: str,
    payload: SaveAssetRequest,
    user_id: str = Depends(get_current_user_id),
):
    project = await Project.get(project_id)
    if not project or project.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    asset = Asset(
        project_id=project_id,
        user_id=user_id,
        source=payload.source,
        source_id=payload.source_id,
        asset_type=payload.asset_type,
        url=payload.url,
        thumbnail_url=payload.thumbnail_url,
        query_used=payload.query_used,
        photographer=payload.photographer,
        saved_at=datetime.now(timezone.utc),
    )
    await asset.insert()
    return serialize_document(asset)


@router.get("/projects/{project_id}/assets")
async def list_project_assets(project_id: str, user_id: str = Depends(get_current_user_id)):
    project = await Project.get(project_id)
    if not project or project.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    assets = await Asset.find(Asset.project_id == project_id, Asset.user_id == user_id).sort("-saved_at").to_list()
    return [serialize_document(asset) for asset in assets]


@router.delete("/assets/{asset_id}")
async def delete_asset(asset_id: str, user_id: str = Depends(get_current_user_id)):
    asset = await Asset.get(asset_id)
    if not asset or asset.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found")

    await asset.delete()
    return {"deleted": True, "asset_id": asset_id}
