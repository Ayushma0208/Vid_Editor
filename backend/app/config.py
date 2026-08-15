import re
import sys
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_WINDOWS_DRIVE_RE = re.compile(r"^[A-Za-z]:[\\/]")


def normalize_temp_dir(value: str) -> str:
    """Force a usable temp root on the current OS (reject Windows drive letters on Unix)."""
    raw = (value or "").strip() or "/tmp/videoedit"
    if sys.platform != "win32" and _WINDOWS_DRIVE_RE.match(raw):
        print(
            f"[config] TEMP_DIR={raw!r} is a Windows path; using /tmp/videoedit on this host.",
            flush=True,
        )
        raw = "/tmp/videoedit"
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = Path("/tmp/videoedit")
    path.mkdir(parents=True, exist_ok=True)
    return str(path.resolve())


class Settings(BaseSettings):
    mongodb_uri: str
    mongodb_db_name: str
    cloudinary_cloud_name: str = ""
    cloudinary_api_key: str = ""
    cloudinary_api_secret: str = ""
    cloudinary_url: str = ""
    pexels_api_key: str = ""
    pixabay_api_key: str = ""
    youtube_client_id: str = ""
    youtube_client_secret: str = ""
    youtube_api_key: str = ""
    instagram_app_id: str = ""
    instagram_app_secret: str = ""
    instagram_redirect_uri: str = ""
    redis_url: str = ""
    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 1440
    temp_dir: str = "/tmp/videoedit"
    default_clip_duration_seconds: int = 60  # 60 seconds per clip (Instagram Reels)
    max_upload_size_bytes: int = 5 * 1024 * 1024 * 1024  # 5 GB
    ad_clip_path: str = ""
    default_ad_duration_seconds: int = 10
    openai_api_key: str = ""
    gemini_api_key: str = ""
    # Total audio budget for Whisper (spread across start/middle/end samples).
    summary_sample_seconds: int = 300
    summary_segment_seconds: int = 60  # length of each sample window
    summary_max_segments: int = 5  # cap number of windows (start → end)
    # External copy-pool API for ready-made Instagram captions.
    copy_pool_base_url: str = ""
    copy_pool_api_key: str = ""
    instagram_publish_delay_seconds: int = 30  # delay between auto-published Reels
    # Non-AI clip interest scoring (audio energy + scene motion).
    interest_audio_weight: float = 0.55
    interest_motion_weight: float = 0.45
    interest_scene_threshold: float = 0.3
    interest_recommend_percentile: float = 0.25  # top 25% marked recommended
    # Multi-quality full-movie pipeline
    target_qualities: str = "240,480,720,1080"
    quality_host_240: str = "uploadrar"
    quality_host_480: str = "up4ever"
    quality_host_720: str = "up4ever"
    quality_host_1080: str = "krakenfiles"
    clip_source_quality: str = "720"
    clip_ttl_days: int = 7
    frontend_url: str = "http://localhost:3000"
    yt_dlp_cookies_file: str = ""
    ftp_host: str = ""
    ftp_port: int = 21
    ftp_user: str = ""
    ftp_password: str = ""
    ftp_remote_dir: str = "/"
    ftp_public_base_url: str = ""
    krakenfiles_api_key: str = ""
    krakenfiles_base_url: str = "https://www.krakenfiles.com"
    uploadrar_api_key: str = ""
    uploadrar_base_url: str = "https://uploadrar.com"
    up4ever_api_key: str = ""
    up4ever_base_url: str = "https://up-4ever.net"

    @field_validator("temp_dir", mode="before")
    @classmethod
    def _normalize_temp_dir(cls, value: object) -> str:
        return normalize_temp_dir("" if value is None else str(value))

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


settings = Settings()
