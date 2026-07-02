import asyncio

from app.config import settings


async def redis_available() -> bool:
    client = None
    try:
        from redis.asyncio import from_url as redis_from_url

        client = redis_from_url(settings.redis_url, socket_connect_timeout=1)
        await client.ping()
        return True
    except Exception:
        return False
    finally:
        if client is not None:
            try:
                close = getattr(client, "aclose", None) or getattr(client, "close", None)
                if close is not None:
                    result = close()
                    if asyncio.iscoroutine(result):
                        await result
            except Exception:
                pass


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
