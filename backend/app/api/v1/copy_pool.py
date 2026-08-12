from fastapi import APIRouter, Depends, HTTPException, Query, Response

from app.api.dependencies import get_current_user_id
from app.services.copy_pool_service import CopyPoolError, CopyPoolService

router = APIRouter(prefix="/copy-pool", tags=["copy-pool"])


@router.get("/descriptions/random")
async def get_random_copy_pool_description(
    response: Response,
    exclude: str | None = Query(
        default=None,
        description="Comma-separated template ids to skip (max 50)",
    ),
    since: str | None = Query(default=None),
    until: str | None = Query(default=None),
    date_field: str | None = Query(default=None, alias="dateField"),
    extract_status: str | None = Query(default=None, alias="extractStatus"),
    enabled: bool | None = Query(default=True),
    q: str | None = Query(default=None, max_length=80),
    hashtag: str | None = Query(default=None),
    _user_id: str = Depends(get_current_user_id),
):
    exclude_ids = [part.strip() for part in (exclude or "").split(",") if part.strip()][:50]
    service = CopyPoolService()
    try:
        data = await service.get_random_description(
            exclude=exclude_ids or None,
            since=since,
            until=until,
            date_field=date_field,
            extract_status=extract_status,
            enabled=enabled,
            q=q,
            hashtag=hashtag,
        )
    except CopyPoolError as exc:
        if exc.retry_after is not None:
            response.headers["Retry-After"] = str(exc.retry_after)
        raise HTTPException(
            status_code=exc.status_code,
            detail={
                "success": False,
                "code": exc.code,
                "message": exc.message,
                "errors": exc.errors,
            },
        ) from exc

    return {"success": True, "data": data}
