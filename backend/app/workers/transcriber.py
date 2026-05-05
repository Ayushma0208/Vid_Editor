import os
import json
import glob
import whisper
from app.config import settings
from app.workers.celery_app import celery_app

@celery_app.task(name="app.workers.transcriber.transcribe_video")
def transcribe_video(job_id: str) -> dict:
    download_dir = os.path.join(settings.LOCAL_MEDIA_PATH, "downloads", job_id)
    video_files = glob.glob(os.path.join(download_dir, "*.mp4"))
    if not video_files:
        raise FileNotFoundError(f"No mp4 found in {download_dir}")

    video_path = video_files[0]
    model = whisper.load_model("base")
    result = model.transcribe(video_path, word_timestamps=True)

    # Save full transcript
    transcript_path = os.path.join(download_dir, "transcript.json")
    with open(transcript_path, "w") as f:
        json.dump(result, f)

    return {"job_id": job_id, "transcript_path": transcript_path}
