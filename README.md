# Movie Clips / Clip AI

Upload long videos and automatically split them into 50-second clips.

## Quick start (Docker)

Prerequisites: [Docker](https://docs.docker.com/get-docker/) and Docker Compose.

1. Copy env template and fill secrets (Cloudinary, JWT, etc.):

```bash
cp .env.example .env
```

2. Build and start everything (MongoDB, Redis, API, Celery worker, frontend):

```bash
docker compose up --build
```

3. Open the app:

- Frontend: http://localhost:3000
- Backend API docs: http://localhost:8000/docs

Stop with `Ctrl+C`, or run detached:

```bash
docker compose up --build -d
docker compose down
```

### Services

| Service   | Role                         | Port |
|-----------|------------------------------|------|
| frontend  | Next.js UI                   | 3000 |
| backend   | FastAPI API                  | 8000 |
| worker    | Celery (clips / downloads)   | —    |
| mongo     | MongoDB                      | 27017|
| redis     | Celery broker / cache        | 6379 |

Compose points the API and worker at the local `mongo` and `redis` containers (not Atlas / remote Redis). Shared clip files live in the `videoedit-temp` volume.

### Use MongoDB Atlas instead

In `docker-compose.yml`, remove or comment the `MONGODB_URI` lines under `backend` and `worker` `environment`, and set your Atlas URI in `.env`.

## Local development (without Docker)

### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
# configure backend/.env
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
celery -A app.celery_worker.celery_app worker --loglevel=info
```

### Frontend

```bash
cd frontend
npm install
NEXT_PUBLIC_API_URL=http://localhost:8000 npm run dev
```

Infra only (Mongo + Redis):

```bash
docker compose up mongo redis
```
