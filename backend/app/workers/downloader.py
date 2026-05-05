import os
import yt_dlp
from app.config import settings
from app.workers.celery_app import celery_app

@celery_app.task(name="app.workers.downloader.download_video")
def download_video(job_id: str) -> dict:
    import asyncio
    from app.workers._helpers import update_job_status
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
    from sqlalchemy import select
    from app.models.job import Job
    from app.models.project import Project

    async def get_youtube_url():
        engine = create_async_engine(settings.ASYNC_DATABASE_URL)
        Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with Session() as session:
            job = await session.get(Job, job_id)
            project = await session.get(Project, job.project_id)
            return project.youtube_url

    youtube_url = asyncio.run(get_youtube_url())
    output_dir = os.path.join(settings.LOCAL_MEDIA_PATH, "downloads", job_id)
    os.makedirs(output_dir, exist_ok=True)

    ydl_opts = {
        "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "outtmpl": os.path.join(output_dir, "%(title)s.%(ext)s"),
        "quiet": True,
        "no_warnings": True,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(youtube_url, download=True)
        title = info.get("title", "video")
        thumbnail = info.get("thumbnail", "")
        filename = ydl.prepare_filename(info)

    # Update project title + thumbnail
    async def update_project():
        engine = create_async_engine(settings.ASYNC_DATABASE_URL)
        Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        from sqlalchemy import update
        from app.models.project import Project
        from app.models.job import Job
        async with Session() as session:
            job = await session.get(Job, job_id)
            await session.execute(
                update(Project).where(Project.id == job.project_id)
                .values(title=title, thumbnail=thumbnail)
            )
            await session.commit()

    asyncio.run(update_project())
    return {"job_id": job_id, "file_path": filename, "title": title}
