import asyncio

from redis.asyncio import from_url as redis_from_url

from app.config import settings


async def redis_available() -> bool:
    client = redis_from_url(settings.redis_url, socket_connect_timeout=1)
    try:
        await client.ping()
        return True
    except Exception:
        return False
    finally:
        await client.aclose()


async def celery_workers_available() -> bool:
    if not await redis_available():
        return False
    try:
        from app.celery_worker import celery_app

        inspector = await asyncio.to_thread(celery_app.control.inspect, timeout=0.5)
        if not inspector:
            return False
        ping = await asyncio.to_thread(inspector.ping)
        return bool(ping)
    except Exception:
        return False
