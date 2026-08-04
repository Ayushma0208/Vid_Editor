import logging
import re
from pathlib import Path
from typing import Any

import httpx

from app.config import settings
from app.services.ffmpeg_service import FfmpegService

logger = logging.getLogger(__name__)

_SUMMARY_SYSTEM_PROMPT = (
    "You write short Instagram Reel captions that summarize an entire movie or long video. "
    "Return 2-4 sentences (max ~400 characters) describing what the full video is about. "
    "No spoilers of the ending. No hashtags unless naturally useful. Plain text only."
)


class SummaryService:
    def __init__(self) -> None:
        self._ffmpeg = FfmpegService()

    def _duration_label(self, duration_seconds: float | None) -> str:
        if not duration_seconds or duration_seconds < 1:
            return ""
        total = int(duration_seconds)
        hours, rem = divmod(total, 3600)
        minutes = rem // 60
        if hours:
            return f"{hours}h {minutes}m"
        return f"{minutes}m"

    def _clean_text(self, text: str, max_len: int = 400) -> str:
        cleaned = re.sub(r"\s+", " ", (text or "").strip())
        if len(cleaned) <= max_len:
            return cleaned
        truncated = cleaned[: max_len - 1].rsplit(" ", 1)[0]
        return (truncated or cleaned[: max_len - 1]).rstrip(".,;:") + "…"

    def _fallback_summary(self, title: str, metadata: dict[str, Any] | None, duration_seconds: float | None) -> str:
        meta = metadata or {}
        description = str(meta.get("description") or meta.get("desc") or "").strip()
        if description:
            # Prefer the first meaningful paragraph from a YouTube/source description.
            first = re.split(r"\n{2,}", description)[0].strip()
            first = re.sub(r"https?://\S+", "", first).strip()
            if len(first) >= 20:
                return self._clean_text(first, 400)

        duration_label = self._duration_label(duration_seconds)
        base = (title or "This video").strip()
        if duration_label:
            return (
                f"{base} — a {duration_label} full-length video cut into short Instagram Reels. "
                "Watch each part to follow the complete story."
            )
        return (
            f"{base} — full video cut into short Instagram Reels. "
            "Watch each part to follow the complete story."
        )

    async def _transcribe_openai(self, audio_path: Path) -> str:
        api_key = (settings.openai_api_key or "").strip()
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is not configured")

        async with httpx.AsyncClient(timeout=180) as client:
            with audio_path.open("rb") as audio_file:
                response = await client.post(
                    "https://api.openai.com/v1/audio/transcriptions",
                    headers={"Authorization": f"Bearer {api_key}"},
                    files={"file": (audio_path.name, audio_file, "audio/mpeg")},
                    data={"model": "whisper-1", "response_format": "text"},
                )
            response.raise_for_status()
            return (response.text or "").strip()

    async def _summarize_openai(self, title: str, transcript: str, duration_seconds: float | None) -> str:
        api_key = (settings.openai_api_key or "").strip()
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is not configured")

        duration_label = self._duration_label(duration_seconds)
        user_prompt = (
            f"Video title: {title or 'Untitled'}\n"
            f"Full duration: {duration_label or 'unknown'}\n\n"
            f"Transcript sample from the start of the video:\n{transcript[:6000]}"
        )
        async with httpx.AsyncClient(timeout=90) as client:
            response = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "gpt-4o-mini",
                    "temperature": 0.4,
                    "messages": [
                        {"role": "system", "content": _SUMMARY_SYSTEM_PROMPT},
                        {"role": "user", "content": user_prompt},
                    ],
                },
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
            return self._clean_text(str(content), 500)

    async def _summarize_gemini(self, title: str, source_text: str, duration_seconds: float | None) -> str:
        api_key = (settings.gemini_api_key or "").strip()
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY is not configured")

        duration_label = self._duration_label(duration_seconds)
        prompt = (
            f"{_SUMMARY_SYSTEM_PROMPT}\n\n"
            f"Video title: {title or 'Untitled'}\n"
            f"Full duration: {duration_label or 'unknown'}\n\n"
            f"Source text:\n{source_text[:8000]}"
        )
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"gemini-2.0-flash:generateContent?key={api_key}"
        )
        async with httpx.AsyncClient(timeout=90) as client:
            response = await client.post(
                url,
                json={"contents": [{"parts": [{"text": prompt}]}]},
            )
            response.raise_for_status()
            payload = response.json()
            parts = payload.get("candidates", [{}])[0].get("content", {}).get("parts", [])
            text = "".join(str(part.get("text", "")) for part in parts).strip()
            if not text:
                raise RuntimeError("Gemini returned an empty summary")
            return self._clean_text(text, 500)

    async def generate_project_summary(
        self,
        *,
        title: str,
        local_video_path: str | None,
        metadata: dict[str, Any] | None,
        duration_seconds: float | None,
        work_dir: Path,
    ) -> str:
        """
        Build a short full-video summary for Instagram captions.

        Preference order:
        1) OpenAI Whisper transcript + GPT summary (needs OPENAI_API_KEY + local video)
        2) Gemini text summary from YouTube description / title (needs GEMINI_API_KEY)
        3) Deterministic fallback from description / title
        """
        meta = metadata or {}
        description = str(meta.get("description") or meta.get("desc") or "").strip()
        openai_key = (settings.openai_api_key or "").strip()
        gemini_key = (settings.gemini_api_key or "").strip()

        transcript = ""
        video_path = Path(local_video_path) if local_video_path else None
        if openai_key and video_path and video_path.is_file():
            audio_path = work_dir / "summary_sample.mp3"
            try:
                sample_seconds = max(60, int(settings.summary_sample_seconds or 300))
                await self._ffmpeg.extract_audio_segment(
                    str(video_path),
                    str(audio_path),
                    start_time=0.0,
                    duration_seconds=float(sample_seconds),
                )
                transcript = await self._transcribe_openai(audio_path)
            except Exception:
                logger.exception("Audio transcription failed; falling back to metadata summary")
            finally:
                if audio_path.exists():
                    try:
                        audio_path.unlink()
                    except OSError:
                        pass

        if openai_key and transcript:
            try:
                return await self._summarize_openai(title, transcript, duration_seconds)
            except Exception:
                logger.exception("OpenAI summarization failed")

        source_for_gemini = transcript or description or title
        if gemini_key and source_for_gemini:
            try:
                return await self._summarize_gemini(title, source_for_gemini, duration_seconds)
            except Exception:
                logger.exception("Gemini summarization failed")

        return self._fallback_summary(title, meta, duration_seconds)
