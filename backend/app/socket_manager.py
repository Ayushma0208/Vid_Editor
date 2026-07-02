import socketio
from app.config import settings

# Use Redis manager when configured, otherwise keep an in-memory manager.
if settings.redis_url:
    client_mgr = socketio.AsyncRedisManager(settings.redis_url)
else:
    client_mgr = socketio.AsyncManager()

# Setup the Server
sio = socketio.AsyncServer(
    async_mode="asgi",
    client_manager=client_mgr,
    cors_allowed_origins=[settings.frontend_url]
)

@sio.event
async def connect(sid, environ):
    pass

@sio.event
async def disconnect(sid):
    pass

@sio.event
async def subscribe_job(sid, job_id):
    await sio.enter_room(sid, str(job_id))

@sio.event
async def unsubscribe_job(sid, job_id):
    await sio.leave_room(sid, str(job_id))

# Expose a generic emitter for the worker tasks to use entirely synchronously or asynchronously
async def emit_job_progress(job_id: str, status: str, progress: int, message: str = ""):
    await sio.emit(
        "job_progress",
        {"job_id": job_id, "status": status, "progress": progress, "message": message},
        room=str(job_id)
    )
