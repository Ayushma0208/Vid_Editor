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
    default_clip_duration_seconds: int = 50  # 50 seconds per clip
    max_upload_size_bytes: int = 5 * 1024 * 1024 * 1024  # 5 GB
    ad_clip_path: str = ""
    default_ad_duration_seconds: int = 10
    frontend_url: str = "http://localhost:3000"
    yt_dlp_cookies_file: str = ""
    ftp_host: str = ""
    ftp_port: int = 21
    ftp_user: str = ""
    ftp_password: str = ""
    ftp_remote_dir: str = "/"
    ftp_public_base_url: str = ""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


settings = Settings()
