import os
import json
import glob
from app.config import settings
from app.workers.celery_app import celery_app

CLIP_SELECTION_PROMPT = """
You are an expert short-form video editor.
Analyze the following video transcript and identify 5-8 segments that would make
excellent viral short clips (30-60 seconds each) for YouTube Shorts, Instagram Reels, and TikTok.

For each clip return JSON with:
- start: float (start time in seconds)
- end: float (end time in seconds)
- title: string (catchy title for the clip)
- hook: string (what makes this clip engaging)
- keywords: list of strings (relevant keywords for B-roll search)

Return ONLY a JSON array. No explanation. No markdown.

TRANSCRIPT:
{transcript_text}
"""

@celery_app.task(name="app.workers.clip_selector.select_clips")
def select_clips(job_id: str) -> dict:
    import asyncio
    from anthropic import Anthropic
    from app.workers._helpers import update_job_status
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
    from sqlalchemy import insert
    from app.models.job import Job
    from app.models.clip import Clip

    download_dir = os.path.join(settings.LOCAL_MEDIA_PATH, "downloads", job_id)
    transcript_path = os.path.join(download_dir, "transcript.json")

    with open(transcript_path) as f:
        transcript = json.load(f)

    # Flatten to plain text
    transcript_text = " ".join(
        seg["text"] for seg in transcript.get("segments", [])
    )

    client = Anthropic(api_key=settings.ANTHROPIC_API_KEY)
    message = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=2000,
        messages=[{"role": "user", "content": CLIP_SELECTION_PROMPT.format(transcript_text=transcript_text[:15000])}],
    )

    clips_data = json.loads(message.content[0].text)

    async def save_clips():
        engine = create_async_engine(settings.ASYNC_DATABASE_URL)
        Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        import uuid
        async with Session() as session:
            for i, c in enumerate(clips_data):
                duration = c["end"] - c["start"]
                clip = Clip(
                    id=str(uuid.uuid4()),
                    job_id=job_id,
                    title=c.get("title", f"Clip {i+1}"),
                    start_time=c["start"],
                    end_time=c["end"],
                    duration=duration,
                    transcript_segment=c.get("hook", ""),
                    order_index=i,
                )
                session.add(clip)
            await session.commit()

    asyncio.run(save_clips())

    keywords_path = os.path.join(download_dir, "clip_keywords.json")
    with open(keywords_path, "w") as f:
        json.dump([c.get("keywords", []) for c in clips_data], f)

    return {"job_id": job_id, "clip_count": len(clips_data)}
