from __future__ import annotations

from typing import Any

from app.config import settings
from app.services.ppd_routing import HOST_KEYS, get_configured_hosts

TARGET_QUALITY_KEYS = ("240", "480", "720", "1080")


def parse_target_qualities() -> list[int]:
    raw = (settings.target_qualities or "240,480,720,1080").strip()
    heights: list[int] = []
    for part in raw.split(","):
        digits = "".join(ch for ch in part.strip() if ch.isdigit())
        if not digits:
            continue
        height = int(digits)
        if height not in heights:
            heights.append(height)
    return heights or [240, 480, 720, 1080]


def quality_key(height: int | str) -> str:
    return str(int("".join(ch for ch in str(height) if ch.isdigit()) or 0))


def get_quality_host_map() -> dict[str, str]:
    return {
        "240": (settings.quality_host_240 or "uploadrar").strip().lower(),
        "480": (settings.quality_host_480 or "up4ever").strip().lower(),
        "720": (settings.quality_host_720 or "up4ever").strip().lower(),
        "1080": (settings.quality_host_1080 or "krakenfiles").strip().lower(),
    }


def host_for_quality(height: int | str) -> str | None:
    key = quality_key(height)
    host = get_quality_host_map().get(key)
    if host and host in HOST_KEYS:
        return host
    return None


def nearest_target_quality(height: int | None) -> str:
    """Map a probed height to the closest configured target bucket."""
    targets = parse_target_qualities()
    if not height or height < 1:
        return settings.clip_source_quality or "720"
    closest = min(targets, key=lambda t: abs(t - int(height)))
    return quality_key(closest)


def empty_quality_asset(height: int | str, *, status: str = "pending") -> dict[str, Any]:
    key = quality_key(height)
    return {
        "status": status,
        "local_path": None,
        "file_size_bytes": None,
        "height": int(key) if key.isdigit() else None,
        "host": host_for_quality(key),
        "host_status": "pending",
        "host_url": None,
        "host_error": None,
        "file_code": None,
    }


def init_quality_assets() -> dict[str, dict[str, Any]]:
    return {quality_key(h): empty_quality_asset(h, status="pending") for h in parse_target_qualities()}


def build_quality_distribute_plan(quality_assets: dict[str, dict[str, Any]] | None) -> dict[str, Any]:
    configured = get_configured_hosts()
    assets = quality_assets or {}
    items: list[dict[str, Any]] = []
    for key in TARGET_QUALITY_KEYS:
        asset = dict(assets.get(key) or empty_quality_asset(key, status="missing"))
        host = asset.get("host") or host_for_quality(key)
        host_configured = bool(host and host in configured)
        items.append(
            {
                "quality": key,
                "status": asset.get("status"),
                "local_path": asset.get("local_path"),
                "file_size_bytes": asset.get("file_size_bytes"),
                "host": host,
                "host_configured": host_configured,
                "host_status": asset.get("host_status"),
                "host_url": asset.get("host_url"),
                "host_error": asset.get("host_error"),
            }
        )
    return {"qualities": items, "configured_hosts": sorted(configured)}
