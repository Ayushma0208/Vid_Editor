import os
from app.config import settings
from app.workers.celery_app import celery_app

@celery_app.task(name="app.workers.viral_scorer.score_clips")
def score_clips(job_id: str) -> dict:
    import asyncio
    import json
    from anthropic import Anthropic
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
    from sqlalchemy import select, update
    from app.models.clip import Clip

    SCORE_PROMPT = """
Rate this video clip segment for viral potential on a scale of 0.0 to 10.0.

Title: {title}
Hook/Description: {hook}
Duration: {duration} seconds

Return ONLY a JSON object:
{{"score": 7.5, "reason": "brief reason"}}
"""

    async def get_and_score():
        engine = create_async_engine(settings.ASYNC_DATABASE_URL)
        Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        client = Anthropic(api_key=settings.ANTHROPIC_API_KEY)

        async with Session() as session:
            result = await session.execute(select(Clip).where(Clip.job_id == job_id))
            clips = result.scalars().all()

            for clip in clips:
                try:
                    msg = client.messages.create(
                        model="claude-haiku-4-5-20251001",
                        max_tokens=200,
                        messages=[{"role": "user", "content": SCORE_PROMPT.format(
                            title=clip.title or "",
                            hook=clip.transcript_segment or "",
                            duration=clip.duration,
                        )}],
                    )
                    result_data = json.loads(msg.content[0].text)
                    score = float(result_data.get("score", 5.0))
                except Exception:
                    score = 5.0

                await session.execute(
                    update(Clip).where(Clip.id == clip.id).values(viral_score=score)
                )

            await session.commit()

    asyncio.run(get_and_score())
    return {"job_id": job_id}
