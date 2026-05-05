import os
import json
from app.config import settings
from app.workers.celery_app import celery_app

@celery_app.task(name="app.workers.caption_burner.burn_captions")
def burn_captions(job_id: str) -> dict:
    import asyncio
    import uuid
    import ffmpeg
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
    from sqlalchemy import select
    from app.models.clip import Clip
    from app.models.caption import Caption

    download_dir = os.path.join(settings.LOCAL_MEDIA_PATH, "downloads", job_id)
    clips_dir = os.path.join(settings.LOCAL_MEDIA_PATH, "clips", job_id)
    transcript_path = os.path.join(download_dir, "transcript.json")

    with open(transcript_path) as f:
        transcript = json.load(f)

    all_words = []
    for seg in transcript.get("segments", []):
        for word_info in seg.get("words", []):
            all_words.append(word_info)

    async def get_clips():
        engine = create_async_engine(settings.ASYNC_DATABASE_URL)
        Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with Session() as session:
            result = await session.execute(select(Clip).where(Clip.job_id == job_id))
            return result.scalars().all()

    clips = asyncio.run(get_clips())

    async def save_captions(captions_data):
        engine = create_async_engine(settings.ASYNC_DATABASE_URL)
        Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with Session() as session:
            for cap in captions_data:
                session.add(Caption(**cap))
            await session.commit()

    for clip in clips:
        clip_words = [
            w for w in all_words
            if w.get("start", 0) >= clip.start_time and w.get("end", 0) <= clip.end_time
        ]

        srt_path = os.path.join(clips_dir, f"{clip.id}.srt")
        captions_to_save = []

        with open(srt_path, "w") as srt_file:
            for i, word in enumerate(clip_words):
                start_rel = word["start"] - clip.start_time
                end_rel = word["end"] - clip.start_time

                def fmt(t):
                    h, r = divmod(int(t), 3600)
                    m, s = divmod(r, 60)
                    ms = int((t - int(t)) * 1000)
                    return f"{h:02}:{m:02}:{s:02},{ms:03}"

                srt_file.write(f"{i+1}\n{fmt(start_rel)} --> {fmt(end_rel)}\n{word['word'].strip()}\n\n")
                captions_to_save.append({
                    "id": str(uuid.uuid4()),
                    "clip_id": clip.id,
                    "start": start_rel,
                    "end": end_rel,
                    "text": word["word"].strip(),
                })

        asyncio.run(save_captions(captions_to_save))

        in_path = os.path.join(clips_dir, f"{clip.id}.mp4")
        out_path = os.path.join(clips_dir, f"{clip.id}_captioned.mp4")
        style = "FontSize=18,FontName=Arial,PrimaryColour=&Hffffff,OutlineColour=&H000000,Outline=2,Alignment=2"
        (
            ffmpeg
            .input(in_path)
            .output(out_path, vf=f"subtitles={srt_path}:force_style='{style}'",
                    vcodec="libx264", acodec="aac", preset="fast")
            .overwrite_output()
            .run(quiet=True)
        )

    return {"job_id": job_id, "captions_burned": len(clips)}
