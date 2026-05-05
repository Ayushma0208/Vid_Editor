from celery import Celery
from celery.signals import worker_process_init
import asyncio

from app.config import settings
from app.database import init_db

celery_app = Celery("videoedit", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    imports=("app.tasks.download_task", "app.tasks.clip_task", "app.tasks.publish_task"),
)

worker_loop = None

@worker_process_init.connect
def init_worker_loop(**kwargs):
    global worker_loop
    worker_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(worker_loop)
    worker_loop.run_until_complete(init_db())
