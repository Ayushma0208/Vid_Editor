from pydantic_settings import BaseSettings, SettingsConfigDict


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
    instagram_publish_delay_seconds: int = 30  # delay between auto-published Reels
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

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


settings = Settings()
