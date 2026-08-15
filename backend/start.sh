#!/bin/sh
set -e
cd "$(dirname "$0")"
if ! command -v ffmpeg >/dev/null 2>&1 && command -v apt-get >/dev/null 2>&1; then
  apt-get update && apt-get install -y --no-install-recommends ffmpeg || true
fi
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" --proxy-headers --forwarded-allow-ips='*'
