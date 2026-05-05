from celery import Celery
from app.config import settings

celery_app = Celery(
    "clipai",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=[
        "app.workers.pipeline",
        "app.workers.downloader",
        "app.workers.transcriber",
        "app.workers.clip_selector",
        "app.workers.video_processor",
        "app.workers.caption_burner",
        "app.workers.viral_scorer",
        "app.workers.broll_fetcher",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    worker_prefetch_multiplier=1,     # one task at a time per worker (video is heavy)
    task_acks_late=True,
)
