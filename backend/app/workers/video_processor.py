import os
import glob
import ffmpeg
from app.config import settings
from app.workers.celery_app import celery_app

@celery_app.task(name="app.workers.video_processor.process_clips")
def process_clips(job_id: str) -> dict:
    import asyncio
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
    from sqlalchemy import select, update
    from app.models.clip import Clip

    download_dir = os.path.join(settings.LOCAL_MEDIA_PATH, "downloads", job_id)
    clips_dir = os.path.join(settings.LOCAL_MEDIA_PATH, "clips", job_id)
    os.makedirs(clips_dir, exist_ok=True)

    video_files = glob.glob(os.path.join(download_dir, "*.mp4"))
    if not video_files:
        raise FileNotFoundError("Source video not found")
    source_video = video_files[0]

    async def get_clips():
        engine = create_async_engine(settings.ASYNC_DATABASE_URL)
        Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with Session() as session:
            result = await session.execute(select(Clip).where(Clip.job_id == job_id))
            return result.scalars().all()

    clips = asyncio.run(get_clips())

    async def update_clip_url(clip_id, file_url, thumb_url):
        engine = create_async_engine(settings.ASYNC_DATABASE_URL)
        Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with Session() as session:
            await session.execute(
                update(Clip).where(Clip.id == clip_id)
                .values(file_url=file_url, thumbnail_url=thumb_url)
            )
            await session.commit()

    for clip in clips:
        out_path = os.path.join(clips_dir, f"{clip.id}.mp4")
        thumb_path = os.path.join(clips_dir, f"{clip.id}_thumb.jpg")

        (
            ffmpeg
            .input(source_video, ss=clip.start_time, to=clip.end_time)
            .filter("crop", "ih*9/16", "ih", "(iw-ih*9/16)/2", 0)
            .filter("scale", 1080, 1920)
            .output(out_path, vcodec="libx264", acodec="aac", preset="fast")
            .overwrite_output()
            .run(quiet=True)
        )

        (
            ffmpeg
            .input(out_path, ss=1)
            .output(thumb_path, vframes=1)
            .overwrite_output()
            .run(quiet=True)
        )

        asyncio.run(update_clip_url(clip.id, out_path, thumb_path))

    return {"job_id": job_id, "processed": len(clips)}
