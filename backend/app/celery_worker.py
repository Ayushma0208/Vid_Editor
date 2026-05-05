from celery import Celery

from app.config import settings


celery_app = Celery("videoedit", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    imports=("app.tasks.download_task", "app.tasks.clip_task", "app.tasks.publish_task"),
)
