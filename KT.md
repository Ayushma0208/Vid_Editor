# Vid_Editor - Knowledge Transfer (KT)

## 1) Project Overview

`Vid_Editor` is a full-stack video editing workflow platform focused on:
- creating projects from YouTube videos,
- downloading and processing source media,
- generating/editing clips,
- managing captions and stock assets,
- and preparing clips for publishing to social platforms.

The backend exposes versioned REST APIs (`/api/v1`) and handles heavy media operations through Celery workers.  
The frontend provides a dashboard-driven UX for project creation, clip management, and media preview.

---

## 2) Tech Stack

## Frontend (`frontend`)
- **Framework:** Next.js `16.2.4` (App Router), React `19.2.4`, TypeScript
- **Styling/UI:** Tailwind CSS v4, Radix UI primitives, custom UI components
- **State/Data:** Zustand, TanStack React Query
- **Forms/Validation:** React Hook Form + Zod
- **Networking:** Axios
- **Realtime Client:** Socket.IO client (hook exists)

Primary reference: `frontend/package.json`

## Backend (`backend`)
- **Framework:** FastAPI `0.111.0`, Uvicorn
- **Auth:** JWT (python-jose), passlib/bcrypt
- **Database:** MongoDB via Motor + Beanie ODM
- **Queue/Async jobs:** Celery + Redis
- **Video tooling:** yt-dlp, ffmpeg/ffprobe, ffmpeg-python
- **Media storage/CDN:** Cloudinary
- **External APIs:** Pexels, Pixabay, YouTube Data/API + OAuth, Instagram Graph/API + OAuth
- **Realtime server:** python-socketio (ASGI mount)

Primary references: `backend/requirements.txt`, `backend/app/main.py`, `backend/app/config.py`

## Data/Infrastructure Components
- **MongoDB:** stores users/projects/clips/captions/assets + token/state collections
- **Redis:** Celery broker/result backend + health checks + Socket.IO manager pub/sub
- **Local temp storage:** default `TEMP_DIR=/tmp/videoedit`

---

## 3) Repository Structure

- `frontend/` - Next.js application (UI, pages, stores, API client)
- `backend/` - FastAPI app, models, services, Celery tasks
  - `app/api/v1/` - all versioned REST endpoints
  - `app/models/` - Beanie document models
  - `app/services/` - integrations (yt-dlp, ffmpeg, Cloudinary, publish, stock APIs)
  - `app/tasks/` - Celery task implementations
  - `app/main.py` - app bootstrapping, middleware, health, task-status
- `README.md` - currently empty

---

## 4) Core Domain Models

Main persisted entities:
- **User** - auth identity, profile, account status
- **Project** - source YouTube metadata + processing state + local media paths
- **Clip** - segment of project media, status (`pending/processing/ready/error`), output URLs
- **Caption** - project/clip-scoped text and style payload
- **Asset** - saved external stock media references for a project

Additional collections used directly:
- `refresh_tokens` (auth token rotation)
- `oauth_states` (OAuth CSRF state tracking)
- `user_tokens` (platform access/refresh tokens for publishing)

---

## 5) End-to-End Workflow

## A. Authentication Flow
1. User registers or logs in from frontend.
2. Backend validates credentials and issues access + refresh tokens.
3. Frontend stores tokens and sends bearer token on API calls.
4. Refresh endpoint rotates refresh token and returns a new token pair.

## B. Project Creation from YouTube
1. Frontend posts a YouTube URL.
2. Backend validates URL and fetches metadata via `yt-dlp --dump-json`.
3. Project is created in MongoDB (initial status: `pending`).
4. Download task is enqueued (Celery) or executed via async fallback when worker unavailable.
5. Download pipeline stores source video in local temp dir and marks project `ready` (or `error`).

## C. Clip Processing
1. Frontend requests clip creation with `start_time`, `end_time`, and `clip_type`.
2. Backend validates time boundaries against source duration.
3. Celery task cuts clip via ffmpeg, generates thumbnail, uploads artifacts to Cloudinary.
4. Clip transitions to `ready` and exposes media URLs/public IDs.

## D. Captions and Assets
- Captions can be created/listed/updated/deleted per project (optionally per clip).
- Stock assets are searched from Pexels/Pixabay and saved into project asset library.

## E. Publish Flow
1. User authorizes YouTube/Instagram via OAuth endpoints.
2. Publish endpoint queues Celery publish task.
3. Task uploads clip media to target platform and stores publish metadata/status.

Notes:
- Backend publish capabilities are implemented.
- Frontend publish UI appears mostly placeholder in current code.

---

## 6) Processing and State Transitions

## Project status lifecycle
- `pending` -> `downloading` -> `ready`
- failure path: `pending/downloading` -> `error`
- retry available via `retry-download` endpoint for valid states

## Clip status lifecycle
- `pending` -> `processing` -> `ready`
- failure path: `pending/processing` -> `error`

## Publish status lifecycle (clip-level fields)
- `queued` -> `processing` -> `published`
- failure path to `error`

---

## 7) API Reference (Complete)

Base URL prefix: `/api/v1`  
Auth: bearer token unless stated otherwise.

## System

### `GET /health`
- Purpose: service health (MongoDB + Redis)
- Auth: none
- Response: `{ status, db, redis }`

### `GET /api/v1/tasks/{task_id}`
- Purpose: generic Celery task status
- Auth: none
- Path params: `task_id`
- Response: `{ task_id, state, ready, successful, result }`

## Auth (`/auth`)

### `POST /api/v1/auth/register`
- Purpose: create user + issue tokens
- Body: `{ email, password, full_name? }`
- Success: `201`
- Errors: `409` duplicate email

### `POST /api/v1/auth/login`
- Purpose: login + issue tokens
- Body: `{ email, password }`
- Errors: `401` invalid credentials

### `POST /api/v1/auth/refresh`
- Purpose: rotate refresh token, issue new token pair
- Body: `{ refresh_token }`
- Errors: `401` invalid/expired token

### `GET /api/v1/auth/me`
- Purpose: get current user profile
- Auth: required

## Projects (`/projects`)

### `POST /api/v1/projects/`
- Purpose: create project from YouTube URL and trigger download
- Auth: required
- Body: `{ yt_url }`
- Success: `201`
- Returns: project data + `{ task_id, execution_mode }`
- Errors: `422` invalid URL/metadata issues, `504` metadata timeout

### `POST /api/v1/projects/seed-dummy`
- Purpose: seed project using local media (dev/seed utility)
- Auth: required
- Body: `{ file_name }`
- Success: `201`
- Errors: `422` missing input, `404` file not found

### `GET /api/v1/projects/`
- Purpose: list projects for current user
- Auth: required

### `GET /api/v1/projects/{project_id}`
- Purpose: fetch one project
- Auth: required
- Errors: `404` not found or not owned

### `POST /api/v1/projects/{project_id}/retry-download`
- Purpose: retry download for retryable state
- Auth: required
- Returns: `{ task_id, execution_mode, ...project }`
- Errors: `404` not found, `409` invalid state

### `DELETE /api/v1/projects/{project_id}`
- Purpose: delete project and related entities
- Auth: required

### `GET /api/v1/projects/{project_id}/stream?token=...`
- Purpose: stream source project video
- Auth: query JWT token (video-tag compatible)
- Errors: `401`, `404`

### `GET /api/v1/projects/{project_id}/thumbnail?token=...`
- Purpose: stream project thumbnail
- Auth: query JWT token
- Errors: `401`, `404`

## Clips

### `POST /api/v1/projects/{project_id}/clips`
- Purpose: create clip request + enqueue clip processing task
- Auth: required
- Body: `{ start_time, end_time, clip_type, label? }`
- `clip_type`: `30s | 60s | custom`
- Success: `201`
- Returns: clip + `task_id`
- Errors: `404` project not found, `422` invalid timing

### `GET /api/v1/projects/{project_id}/clips`
- Purpose: list clips for project
- Auth: required

### `GET /api/v1/clips/{clip_id}`
- Purpose: get clip details and status
- Auth: required

### `PATCH /api/v1/clips/{clip_id}`
- Purpose: update clip metadata (currently label update)
- Auth: required
- Body: `{ label }`

### `DELETE /api/v1/clips/{clip_id}`
- Purpose: delete clip and clean media assets
- Auth: required

## Captions

### `POST /api/v1/projects/{project_id}/captions`
- Purpose: create caption (project-level or clip-level)
- Auth: required
- Body: `{ raw_text, clip_id?, lines?, style? }`
- Success: `201`

### `GET /api/v1/projects/{project_id}/captions`
- Purpose: list captions
- Auth: required
- Query: `clip_id` (optional)

### `GET /api/v1/captions/{caption_id}`
- Purpose: get caption details
- Auth: required

### `PATCH /api/v1/captions/{caption_id}`
- Purpose: partial update caption content/style/version
- Auth: required
- Body: any of `{ raw_text, lines, style, ai_processed }`

### `DELETE /api/v1/captions/{caption_id}`
- Purpose: delete caption
- Auth: required

## Assets

### `GET /api/v1/assets/search`
- Purpose: search stock media from Pexels/Pixabay
- Auth: none
- Query:
  - `q` (required)
  - `type` = `image|video|all` (default `image`)
  - `source` = `pexels|pixabay|all` (default `all`)
  - `page` (>=1)
  - `per_page` (1..80)
- Response: `{ results, total, page, per_page }`

### `POST /api/v1/projects/{project_id}/assets`
- Purpose: save selected external asset to project
- Auth: required
- Body: `{ source_id, source, asset_type, url, thumbnail_url?, query_used?, photographer? }`
- Success: `201`
- Errors: `404` project missing, `409` duplicate

### `GET /api/v1/projects/{project_id}/assets`
- Purpose: list saved assets for project
- Auth: required

### `DELETE /api/v1/assets/{asset_id}`
- Purpose: delete saved asset
- Auth: required

## Publishing

### `POST /api/v1/auth/youtube`
- Purpose: initiate YouTube OAuth
- Auth: required
- Response: `{ platform: "youtube", auth_url }`

### `GET /api/v1/auth/youtube/callback?code=...&state=...`
- Purpose: complete YouTube OAuth
- Auth: none (callback endpoint)

### `POST /api/v1/auth/instagram`
- Purpose: initiate Instagram OAuth
- Auth: required
- Response: `{ platform: "instagram", auth_url }`

### `GET /api/v1/auth/instagram/callback?code=...&state=...`
- Purpose: complete Instagram OAuth
- Auth: none (callback endpoint)

### `POST /api/v1/clips/{clip_id}/publish/youtube`
- Purpose: queue YouTube publish task
- Auth: required
- Response: `{ task_id, status: "queued" }`

### `POST /api/v1/clips/{clip_id}/publish/instagram`
- Purpose: queue Instagram publish task
- Auth: required
- Response: `{ task_id, status: "queued" }`

### `GET /api/v1/clips/{clip_id}/publish/status`
- Purpose: get publish execution + persisted status
- Auth: required

## Video Router (placeholder)

### `POST /api/v1/videos/download`
- Purpose: stub endpoint (currently returns placeholder message)

---

## 8) Key Modules and Responsibilities

## Backend
- `app/main.py` - app setup, middleware, global exception shape, health/task endpoints
- `app/api/v1/*.py` - route handlers by domain
- `app/models/*.py` - Beanie documents and schema fields
- `app/services/ytdlp_service.py` - URL normalization, metadata fetch, robust download attempts
- `app/services/ffmpeg_service.py` - clip cutting and media processing helpers
- `app/services/cloudinary_service.py` - upload/delete/URL handling for media assets
- `app/services/publish_service.py` - OAuth state/token lifecycle + platform publishing
- `app/services/pexels_service.py`, `app/services/pixabay_service.py` - stock search adapters
- `app/tasks/download_task.py` - project download task lifecycle
- `app/tasks/clip_task.py` - clip processing and upload lifecycle
- `app/tasks/publish_task.py` - publish execution lifecycle
- `app/socket_manager.py` - realtime socket server and room subscription handlers

## Frontend
- `src/app/dashboard/page.tsx` - project creation and project list
- `src/app/project/[jobId]/clips/page.tsx` - clip workflow page (main operational screen)
- `src/lib/api.ts` - centralized Axios client and auth token handling
- `src/store/*` - Zustand stores for project/clip states
- `src/hooks/useWebSocket.ts` - realtime subscription hook (currently appears underused)

---

## 9) Configuration and Environment Variables

The backend expects `.env` values (sample in `backend/.env.example`):
- `MONGODB_URI`, `MONGODB_DB_NAME`
- `REDIS_URL`
- `JWT_SECRET_KEY`, `JWT_ALGORITHM`, `ACCESS_TOKEN_EXPIRE_MINUTES`
- `TEMP_DIR`, `FRONTEND_URL`
- `CLOUDINARY_CLOUD_NAME`, `CLOUDINARY_API_KEY`, `CLOUDINARY_API_SECRET`
- `PEXELS_API_KEY`, `PIXABAY_API_KEY`
- `YOUTUBE_CLIENT_ID`, `YOUTUBE_CLIENT_SECRET`, `YOUTUBE_API_KEY`
- `INSTAGRAM_APP_ID`, `INSTAGRAM_APP_SECRET`
- optional: `YT_DLP_COOKIES_FILE`

---

## 10) How to Run (Developer Setup)

## Backend
1. Create Python environment.
2. Install dependencies from `backend/requirements.txt`.
3. Configure `backend/.env`.
4. Run FastAPI app (Uvicorn).
5. Run Celery worker pointing to `app.celery_worker.celery_app`.
6. Ensure MongoDB and Redis are running.

## Frontend
1. Install dependencies in `frontend`.
2. Run `npm run dev`.
3. Ensure frontend points to backend API base URL used by `src/lib/api.ts`.

---

## 11) Known Gaps / Implementation Notes

- Socket.IO infrastructure is present, but current task flows do not appear to emit progress events in active pipelines.
- Frontend has websocket hook code but current pages may primarily rely on polling.
- Publishing backend is implemented; frontend publish workflow looks partially scaffolded.
- Root `README.md` is empty; this `KT.md` is currently the primary technical handover document.

---

## 12) Suggested Handover Checklist for Senior Dev

- Validate local run with MongoDB + Redis + Celery worker + frontend dev server.
- Create project from valid YouTube URL and verify `pending -> downloading -> ready`.
- Create clip and verify Cloudinary artifact generation and status updates.
- Test caption CRUD and asset search/save/delete APIs.
- Test OAuth + publish endpoints with valid platform app credentials.
- Confirm operational logging and request IDs in backend output.

