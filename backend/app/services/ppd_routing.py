from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from app.models.clip import Clip
from app.services.krakenfiles_service import KrakenFilesService
from app.services.up4ever_service import Up4everService
from app.services.uploadrar_service import UploadrarService

HOST_KEYS = ("krakenfiles", "uploadrar", "up4ever")

HOST_LABELS: dict[str, str] = {
    "krakenfiles": "KrakenFiles",
    "uploadrar": "Uploadrar",
    "up4ever": "Up-4ever",
}

MB = 1024 * 1024
GB = 1024 * MB


@dataclass(frozen=True)
class SizeBracket:
    name: str
    label: str
    primary: str
    backup: str | None


SIZE_BRACKETS: tuple[tuple[int, int | None, SizeBracket], ...] = (
    (0, 500 * MB, SizeBracket("Small", "0-500MB", "uploadrar", "up4ever")),
    (500 * MB + 1, 1 * GB, SizeBracket("Medium", "500MB-1GB", "uploadrar", "up4ever")),
    (1 * GB + 1, 2 * GB, SizeBracket("Large", "1GB-2GB", "up4ever", "uploadrar")),
    (2 * GB + 1, 5 * GB, SizeBracket("XL", "2GB-5GB", "up4ever", "krakenfiles")),
    (5 * GB + 1, 10 * GB, SizeBracket("XXL", "5GB-10GB", "krakenfiles", "up4ever")),
    (10 * GB + 1, None, SizeBracket("Archive", "10GB+", "krakenfiles", None)),
)


def get_host_service(host: str) -> Any:
    if host == "krakenfiles":
        return KrakenFilesService()
    if host == "uploadrar":
        return UploadrarService()
    if host == "up4ever":
        return Up4everService()
    raise ValueError(f"Unsupported host: {host}")


def get_configured_hosts() -> set[str]:
    return {key for key in HOST_KEYS if get_host_service(key).is_configured()}


def resolve_bracket(size_bytes: int) -> SizeBracket:
    for min_bytes, max_bytes, bracket in SIZE_BRACKETS:
        if size_bytes >= min_bytes and (max_bytes is None or size_bytes <= max_bytes):
            return bracket
    return SIZE_BRACKETS[-1][2]


def resolve_hosts_for_size(size_bytes: int, configured_hosts: set[str]) -> dict[str, Any]:
    bracket = resolve_bracket(size_bytes)
    candidates: list[str] = [bracket.primary]
    if bracket.backup:
        candidates.append(bracket.backup)

    recommended: list[str] = []
    seen: set[str] = set()
    for host in candidates:
        if host in configured_hosts and host not in seen:
            seen.add(host)
            recommended.append(host)

    return {
        "size_bytes": size_bytes,
        "bracket": {"name": bracket.name, "label": bracket.label},
        "primary": bracket.primary,
        "backup": bracket.backup,
        "recommended_hosts": recommended,
    }


def get_clip_size_bytes(clip: Clip) -> int | None:
    if clip.file_size_bytes is not None:
        return clip.file_size_bytes
    if clip.local_clip_path:
        path = Path(clip.local_clip_path)
        if path.is_file():
            return path.stat().st_size
    return None


def get_bracket_table() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for min_bytes, max_bytes, bracket in SIZE_BRACKETS:
        rows.append(
            {
                "name": bracket.name,
                "label": bracket.label,
                "min_bytes": min_bytes,
                "max_bytes": max_bytes,
                "primary": bracket.primary,
                "backup": bracket.backup,
            }
        )
    return rows


def build_recommendations(size_bytes: int) -> dict[str, Any]:
    configured = get_configured_hosts()
    routing = resolve_hosts_for_size(size_bytes, configured)
    primary = routing["primary"]
    backup = routing.get("backup")

    all_hosts: list[dict[str, Any]] = []
    for key in HOST_KEYS:
        role: Literal["primary", "backup"] | None = None
        if key == primary:
            role = "primary"
        elif backup and key == backup:
            role = "backup"
        all_hosts.append(
            {
                "key": key,
                "label": HOST_LABELS[key],
                "configured": key in configured,
                "role": role,
            }
        )

    return {**routing, "all_hosts": all_hosts}
