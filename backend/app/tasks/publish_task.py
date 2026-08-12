import asyncio
from pathlib import Path

from beanie import PydanticObjectId

from app.celery_worker import celery_app
import app.celery_worker as cw
from app.config import settings
from app.models.clip import Clip, ClipStatus
from app.models.project import Project
from app.services.publish_service import PublishService


def _build_instagram_caption(
    *,
    title: str,
    description: str,
    clip_label: str | None,
    part_index: int | None = None,
    part_total: int | None = None,
) -> str:
    body = (description or "").strip()
    parts: list[str] = []

    heading = (title or "").strip()
    if not heading and clip_label:
        heading = clip_label.strip()
    if heading:
        parts.append(heading)

    if body:
        parts.append(body)

    if part_index and part_total and part_total > 1:
        parts.append(f"Part {part_index}/{part_total}")

    caption = "\n\n".join(parts).strip()
    # Instagram caption limit is 2200 characters.
    return caption[:2200]


async def _publish_clip(
    platform: str,
    clip_id: str,
    user_id: str,
    title: str = "",
    description: str = "",
) -> dict:
    clip = await Clip.get(PydanticObjectId(clip_id))
    if not clip or clip.user_id != user_id:
        raise RuntimeError("Clip not found")

    clip.publish_status = "processing"
    await clip.save()

    publish_service = PublishService()
    if platform == "youtube":
        result = await publish_service.upload_youtube(
            user_id=user_id,
            clip=clip,
            description=description,
            title=title,
        )
        clip.published_media_id = result.get("youtube_video_id")
        clip.published_url = result.get("youtube_url")
        local_path = result.get("local_path")
        if local_path:
            file_path = Path(local_path)
            if file_path.exists():
                file_path.unlink()
    elif platform == "instagram":
        siblings = await Clip.find(
            Clip.project_id == clip.project_id,
            Clip.user_id == user_id,
        ).sort("+start_time").to_list()
        part_total = len(siblings) or None
        part_index = None
        for idx, sibling in enumerate(siblings, start=1):
            if str(sibling.id) == str(clip.id):
                part_index = idx
                break

        caption = _build_instagram_caption(
            title=title,
            description=description,
            clip_label=clip.label,
            part_index=part_index,
            part_total=part_total,
        )
        result = await publish_service.upload_instagram(
            user_id=user_id,
            clip=clip,
            caption=caption,
        )
        clip.published_media_id = result.get("instagram_media_id")
        clip.published_url = result.get("permalink")
    else:
        raise RuntimeError("Unsupported platform")

    clip.publish_platform = platform
    clip.publish_status = "published"
    await clip.save()
    return result


async def _publish_all_instagram(
    project_id: str,
    user_id: str,
    title: str = "",
    description: str = "",
    clip_ids: list[str] | None = None,
) -> dict:
    project = await Project.get(PydanticObjectId(project_id))
    if not project or project.user_id != user_id:
        raise RuntimeError("Project not found")

    ready_clips = await Clip.find(
        Clip.project_id == project_id,
        Clip.user_id == user_id,
        Clip.status == ClipStatus.READY,
    ).sort("+start_time").to_list()

    if clip_ids:
        wanted = {cid for cid in clip_ids if cid}
        by_id = {str(c.id): c for c in ready_clips}
        clips = [by_id[cid] for cid in clip_ids if cid in by_id]
        # Keep request order when provided; fall back to chronological for extras.
        if len(clips) != len(wanted):
            missing = wanted - set(by_id.keys())
            # Skip missing ids rather than aborting the whole batch.
            _ = missing
    else:
        clips = ready_clips

    published = 0
    failed = 0
    results: list[dict] = []
    delay = max(0, int(settings.instagram_publish_delay_seconds or 0))

    for index, clip in enumerate(clips):
        clip_id = str(clip.id)
        if not clip.cloudinary_clip_url:
            failed += 1
            results.append({"clip_id": clip_id, "status": "error", "error": "Missing Cloudinary URL"})
            continue
        try:
            result = await _publish_clip(
                platform="instagram",
                clip_id=clip_id,
                user_id=user_id,
                title=(clip.label or title or project.title or ""),
                description=description,
            )
            published += 1
            results.append({"clip_id": clip_id, "status": "published", "result": result})
        except Exception as exc:
            failed += 1
            results.append({"clip_id": clip_id, "status": "error", "error": str(exc)})
            async def _mark_error(cid: str = clip_id) -> None:
                doc = await Clip.get(PydanticObjectId(cid))
                if doc:
                    doc.publish_platform = "instagram"
                    doc.publish_status = "error"
                    await doc.save()

            await _mark_error()

        if delay and index < len(clips) - 1:
            await asyncio.sleep(delay)

    return {
        "project_id": project_id,
        "total": len(clips),
        "published": published,
        "failed": failed,
        "results": results,
    }


@celery_app.task(bind=True, name="publish_clip_task")
def publish_clip_task(
    self,
    platform: str,
    clip_id: str,
    user_id: str,
    title: str = "",
    description: str = "",
):
    try:
        loop = cw.worker_loop if cw.worker_loop is not None else asyncio.get_event_loop()
        return loop.run_until_complete(
            _publish_clip(
                platform=platform,
                clip_id=clip_id,
                user_id=user_id,
                title=title,
                description=description,
            )
        )
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


@celery_app.task(bind=True, name="publish_all_instagram_task")
def publish_all_instagram_task(
    self,
    project_id: str,
    user_id: str,
    title: str = "",
    description: str = "",
    clip_ids: list[str] | None = None,
):
    loop = cw.worker_loop if cw.worker_loop is not None else asyncio.get_event_loop()
    return loop.run_until_complete(
        _publish_all_instagram(
            project_id=project_id,
            user_id=user_id,
            title=title,
            description=description,
            clip_ids=clip_ids,
        )
    )
