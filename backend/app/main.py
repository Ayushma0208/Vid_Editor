import json
import time
import uuid

from celery.result import AsyncResult
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from jose import JWTError, jwt
from redis.asyncio import from_url as redis_from_url

from app.api.v1.router import api_router
from app.celery_worker import celery_app
from app.config import settings
from app.utils.ffmpeg_utils import ensure_ffmpeg_on_path, ffmpeg_available, get_ffmpeg_path, get_ffprobe_path
from app.database import database, init_db
import socketio
from app.socket_manager import sio


app = FastAPI(title="Movie Clips API", version="1.0.0")

# Mount Socket.IO application
socket_app = socketio.ASGIApp(sio, socketio_path="socket.io")
app.mount("/socket.io", socket_app)

app.include_router(api_router, prefix="/api/v1")

def _cors_origins() -> list[str]:
    origins = {
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "https://vid-editor-tan.vercel.app",
    }
    for part in (settings.frontend_url or "").split(","):
        origin = part.strip().rstrip("/")
        if origin:
            origins.add(origin)
    return [item for item in origins if item]


app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    request_id = str(uuid.uuid4())
    request.state.request_id = request_id

    user_id = None
    token = ""
    auth_header = request.headers.get("authorization")
    if auth_header and auth_header.lower().startswith("bearer "):
        token = auth_header.split(" ", 1)[1].strip()
    if not token:
        token = (request.query_params.get("token") or "").strip()
    if token:
        try:
            payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
            user_id = payload.get("sub")
        except JWTError:
            user_id = None
    request.state.user_id = user_id

    start = time.time()
    response = await call_next(request)
    duration_ms = int((time.time() - start) * 1000)
    response.headers["X-Request-ID"] = request_id

    log_line = {
        "request_id": request_id,
        "method": request.method,
        "path": str(request.url.path),
        "status_code": response.status_code,
        "duration_ms": duration_ms,
        "user_id": user_id,
        "project_id": request.path_params.get("project_id") if hasattr(request, "path_params") else None,
    }
    print(json.dumps(log_line))
    return response


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": "http_error",
            "detail": exc.detail,
            "status_code": exc.status_code,
            "request_id": getattr(request.state, "request_id", None),
        },
    )


def _json_safe(value):
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    filename = getattr(value, "filename", None)
    if filename:
        return str(filename)
    return str(value)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    errors = []
    for err in exc.errors():
        item = dict(err)
        item["input"] = _json_safe(item.get("input"))
        item.pop("ctx", None)
        errors.append(item)
    first_msg = next((str(err.get("msg") or "").strip() for err in errors if err.get("msg")), "")
    return JSONResponse(
        status_code=422,
        content={
            "error": "validation_error",
            "detail": first_msg or "Invalid request",
            "errors": errors,
            "status_code": 422,
            "request_id": getattr(request.state, "request_id", None),
        },
    )


@app.on_event("startup")
async def on_startup() -> None:
    ensure_ffmpeg_on_path()
    try:
        await init_db()
    except Exception as exc:
        print(f"[startup] WARNING: database init failed: {exc}")
    if ffmpeg_available():
        print(f"[startup] FFmpeg: {get_ffmpeg_path()}")
        print(f"[startup] FFprobe: {get_ffprobe_path()}")
    else:
        print("[startup] WARNING: FFmpeg/ffprobe not found — video processing will fail")
    try:
        from app.services.pipeline_runtime import recover_stale_pipelines

        await recover_stale_pipelines()
    except Exception as exc:
        print(f"[startup] WARNING: stale pipeline recovery failed: {exc}")


@app.api_route("/", methods=["GET", "HEAD"])
@app.api_route("/health", methods=["GET", "HEAD"])
async def health_check():
    """Liveness probe for Render/Docker — must stay fast and always return 200.

    Do not call Mongo/Redis here: unreachable deps can hang the request and
    cause deploy timeouts even when Uvicorn is running.
    """
    return {"status": "ok"}


@app.get("/ready")
async def readiness_check():
    """Deeper dependency check — not used as the platform health probe."""
    db_status = "ok"
    redis_status = "not_configured"

    try:
        await database.command("ping")
    except Exception:
        db_status = "error"

    if settings.redis_url:
        redis_status = "ok"
        redis_client = redis_from_url(
            settings.redis_url,
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
        )
        try:
            await redis_client.ping()
        except Exception:
            redis_status = "error"
        finally:
            await redis_client.aclose()

    overall = "ok" if db_status == "ok" and redis_status in ("ok", "not_configured") else "degraded"
    status_code = 200 if overall == "ok" else 503
    return JSONResponse(
        status_code=status_code,
        content={"status": overall, "db": db_status, "redis": redis_status},
    )


@app.get("/api/v1/tasks/{task_id}")
async def get_task_status(task_id: str):
    task = AsyncResult(task_id, app=celery_app)
    return {
        "task_id": task_id,
        "state": task.state,
        "ready": task.ready(),
        "successful": task.successful() if task.ready() else None,
        "result": task.result if task.ready() else None,
    }
