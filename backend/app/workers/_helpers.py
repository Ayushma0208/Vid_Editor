from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from app.config import settings
from app.socket_manager import emit_job_progress

_engine = create_async_engine(settings.ASYNC_DATABASE_URL)
_Session = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)

async def update_job_status(job_id: str, status: str, progress: int, error: str = None):
    from app.models.job import Job
    from sqlalchemy import update
    async with _Session() as session:
        stmt = (
            update(Job)
            .where(Job.id == job_id)
            .values(status=status, progress=progress, error_message=error)
        )
        await session.execute(stmt)
        await session.commit()

async def emit_progress(job_id: str, status: str, progress: int, message: str = ""):
    try:
        await emit_job_progress(job_id, status, progress, message)
    except Exception:
        pass  # WebSocket emit is best-effort
