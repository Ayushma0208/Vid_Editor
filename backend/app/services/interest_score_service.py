from __future__ import annotations

import logging
import math
from typing import Any

from app.config import settings
from app.models.clip import Clip, ClipStatus
from app.services.ffmpeg_service import FfmpegService

logger = logging.getLogger(__name__)


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def _audio_score_from_db(mean_volume: float | None, max_volume: float | None) -> float | None:
    """Map volumedetect dB values to 0–100. Silence is ~-91 dB; loud speech/music nearer 0."""
    if mean_volume is None and max_volume is None:
        return None

    # Prefer mean; blend max so short peaks still register.
    mean = mean_volume if mean_volume is not None else max_volume
    peak = max_volume if max_volume is not None else mean
    assert mean is not None and peak is not None

    # Map [-60, -5] dB mean → [0, 100]
    mean_norm = _clamp((mean - (-60.0)) / (55.0) * 100.0)
    peak_norm = _clamp((peak - (-40.0)) / (35.0) * 100.0)
    return round(0.7 * mean_norm + 0.3 * peak_norm, 2)


def _motion_score_from_scenes(scene_count: int | None, duration_seconds: float) -> float | None:
    if scene_count is None:
        return None
    duration = max(float(duration_seconds or 0.0), 1.0)
    # Changes per minute; 0 → 0, ~20+/min → 100
    rate_per_minute = (scene_count / duration) * 60.0
    return round(_clamp((rate_per_minute / 20.0) * 100.0), 2)


class InterestScoreService:
    def __init__(self, ffmpeg: FfmpegService | None = None) -> None:
        self._ffmpeg = ffmpeg or FfmpegService()

    async def score_clip_file(
        self,
        local_path: str,
        *,
        duration_seconds: float | None = None,
    ) -> dict[str, float | None]:
        """Compute audio/motion/combined interest scores. Fail-soft: partial None ok."""
        duration = duration_seconds
        if duration is None or duration <= 0:
            duration = await self._ffmpeg.probe_duration(local_path) or 1.0

        audio_score: float | None = None
        motion_score: float | None = None

        try:
            volume = await self._ffmpeg.probe_volume_stats(local_path)
            if volume:
                audio_score = _audio_score_from_db(
                    volume.get("mean_volume"),
                    volume.get("max_volume"),
                )
        except Exception:
            logger.exception("Audio interest probe failed for %s", local_path)

        try:
            scene_count = await self._ffmpeg.probe_scene_change_count(
                local_path,
                threshold=settings.interest_scene_threshold,
            )
            motion_score = _motion_score_from_scenes(scene_count, float(duration))
        except Exception:
            logger.exception("Motion interest probe failed for %s", local_path)

        combined: float | None = None
        if audio_score is not None or motion_score is not None:
            audio_w = float(settings.interest_audio_weight)
            motion_w = float(settings.interest_motion_weight)
            weight_sum = 0.0
            weighted = 0.0
            if audio_score is not None:
                weighted += audio_w * audio_score
                weight_sum += audio_w
            if motion_score is not None:
                weighted += motion_w * motion_score
                weight_sum += motion_w
            if weight_sum > 0:
                combined = round(_clamp(weighted / weight_sum), 2)

        return {
            "interest_audio": audio_score,
            "interest_motion": motion_score,
            "interest_score": combined,
        }

    async def apply_scores_to_clip(self, clip: Clip, local_path: str) -> Clip:
        scores = await self.score_clip_file(local_path, duration_seconds=clip.duration)
        clip.interest_audio = scores["interest_audio"]
        clip.interest_motion = scores["interest_motion"]
        clip.interest_score = scores["interest_score"]
        return clip


async def mark_recommended_clips(project_id: str, user_id: str | None = None) -> dict[str, Any]:
    """Mark top percentile of scored clips as recommended; clear the rest."""
    if user_id:
        clips = await Clip.find(Clip.project_id == project_id, Clip.user_id == user_id).to_list()
    else:
        clips = await Clip.find(Clip.project_id == project_id).to_list()

    for clip in clips:
        clip.is_recommended = False

    scored = [c for c in clips if c.interest_score is not None and c.status == ClipStatus.READY]
    scored.sort(key=lambda c: float(c.interest_score or 0.0), reverse=True)

    percentile = float(settings.interest_recommend_percentile or 0.25)
    percentile = max(0.01, min(1.0, percentile))

    recommend_count = 0
    if scored:
        recommend_count = max(1, int(math.ceil(len(scored) * percentile)))
        for clip in scored[:recommend_count]:
            clip.is_recommended = True

    for clip in clips:
        await clip.save()

    return {
        "project_id": project_id,
        "scored": len(scored),
        "recommended": recommend_count,
    }
