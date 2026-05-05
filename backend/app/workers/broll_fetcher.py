import os
import json
import httpx
from app.config import settings
from app.workers.celery_app import celery_app

@celery_app.task(name="app.workers.broll_fetcher.fetch_broll")
def fetch_broll(job_id: str) -> dict:
    import asyncio
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
    from sqlalchemy import select
    from app.models.clip import Clip

    download_dir = os.path.join(settings.LOCAL_MEDIA_PATH, "downloads", job_id)
    keywords_path = os.path.join(download_dir, "clip_keywords.json")

    if not os.path.exists(keywords_path):
        return {"job_id": job_id, "broll": []}

    with open(keywords_path) as f:
        all_keywords = json.load(f)

    async def get_clips():
        engine = create_async_engine(settings.ASYNC_DATABASE_URL)
        Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with Session() as session:
            result = await session.execute(select(Clip).where(Clip.job_id == job_id))
            return result.scalars().all()

    clips = asyncio.run(get_clips())
    broll_results = {}

    for i, clip in enumerate(clips):
        keywords = all_keywords[i] if i < len(all_keywords) else []
        if not keywords:
            continue
        query = " ".join(keywords[:3])
        assets = []

        if settings.PEXELS_API_KEY:
            try:
                r = httpx.get(
                    "https://api.pexels.com/videos/search",
                    params={"query": query, "per_page": 3, "orientation": "portrait"},
                    headers={"Authorization": settings.PEXELS_API_KEY},
                    timeout=10,
                )
                for v in r.json().get("videos", []):
                    file = next((f for f in v["video_files"] if f["quality"] == "hd"), v["video_files"][0])
                    assets.append({"type": "video", "url": file["link"], "source": "pexels"})
            except Exception:
                pass

        if settings.PIXABAY_API_KEY and len(assets) < 3:
            try:
                r = httpx.get(
                    "https://pixabay.com/api/",
                    params={"key": settings.PIXABAY_API_KEY, "q": query, "image_type": "photo", "per_page": 3},
                    timeout=10,
                )
                for img in r.json().get("hits", []):
                    assets.append({"type": "image", "url": img["webformatURL"], "source": "pixabay"})
            except Exception:
                pass

        broll_results[clip.id] = assets

    clips_dir = os.path.join(settings.LOCAL_MEDIA_PATH, "clips", job_id)
    os.makedirs(clips_dir, exist_ok=True)
    with open(os.path.join(clips_dir, "broll_assets.json"), "w") as f:
        json.dump(broll_results, f)

    return {"job_id": job_id, "broll_fetched": len(broll_results)}
