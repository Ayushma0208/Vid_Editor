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
from app.database import database
from app.database import init_db
import socketio
from app.socket_manager import sio


app = FastAPI(title="Movie Clips API", version="1.0.0")

# Mount Socket.IO application
socket_app = socketio.ASGIApp(sio, socketio_path="socket.io")
app.mount("/socket.io", socket_app)

app.include_router(api_router, prefix="/api/v1")
allowed_origins = list(
    {
        settings.frontend_url.rstrip("/"),
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    }
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    request_id = str(uuid.uuid4())
    request.state.request_id = request_id

    user_id = None
    auth_header = request.headers.get("authorization")
    if auth_header and auth_header.lower().startswith("bearer "):
        token = auth_header.split(" ", 1)[1]
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


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={
            "error": "validation_error",
            "detail": exc.errors(),
            "status_code": 422,
            "request_id": getattr(request.state, "request_id", None),
        },
    )


@app.on_event("startup")
async def on_startup() -> None:
    await init_db()


@app.get("/health")
async def health_check():
    db_status = "ok"
    redis_status = "ok"

    try:
        await database.command("ping")
    except Exception:
        db_status = "error"

    redis_client = redis_from_url(settings.redis_url, decode_responses=True)
    try:
        await redis_client.ping()
    except Exception:
        redis_status = "error"
    finally:
        await redis_client.aclose()

    overall = "ok" if db_status == "ok" and redis_status == "ok" else "degraded"
    return {"status": overall, "db": db_status, "redis": redis_status}


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
