import asyncio
from pathlib import Path

from beanie import PydanticObjectId

from app.celery_worker import celery_app
import app.celery_worker as cw
from app.models.clip import Clip
from app.services.publish_service import PublishService

async def _publish_clip(platform: str, clip_id: str, user_id: str) -> dict:
    clip = await Clip.get(PydanticObjectId(clip_id))
    if not clip or clip.user_id != user_id:
        raise RuntimeError("Clip not found")

    clip.publish_status = "processing"
    await clip.save()

    publish_service = PublishService()
    if platform == "youtube":
        result = await publish_service.upload_youtube(user_id=user_id, clip=clip)
        clip.published_media_id = result.get("youtube_video_id")
        clip.published_url = result.get("youtube_url")
        local_path = result.get("local_path")
        if local_path:
            file_path = Path(local_path)
            if file_path.exists():
                file_path.unlink()
    elif platform == "instagram":
        result = await publish_service.upload_instagram(user_id=user_id, clip=clip)
        clip.published_media_id = result.get("instagram_media_id")
        clip.published_url = result.get("permalink")
    else:
        raise RuntimeError("Unsupported platform")

    clip.publish_platform = platform
    clip.publish_status = "published"
    await clip.save()
    return result


@celery_app.task(bind=True, name="publish_clip_task")
def publish_clip_task(self, platform: str, clip_id: str, user_id: str):
    try:
        loop = cw.worker_loop if cw.worker_loop is not None else asyncio.get_event_loop()
        return loop.run_until_complete(_publish_clip(platform=platform, clip_id=clip_id, user_id=user_id))
    except Exception as exc:
        async def _mark_error() -> None:
            clip = await Clip.get(PydanticObjectId(clip_id))
            if clip:
                clip.publish_platform = platform
                clip.publish_status = "error"
                await clip.save()

        loop = cw.worker_loop if cw.worker_loop is not None else asyncio.get_event_loop()
        loop.run_until_complete(_mark_error())
        raise exc
