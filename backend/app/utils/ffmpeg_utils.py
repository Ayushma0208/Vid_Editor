import shutil


def ffmpeg_missing_message() -> str:
    return (
        "FFmpeg/ffprobe is not installed or not on PATH. "
        "Install it with: winget install Gyan.FFmpeg — then restart the backend and click Retry."
    )


def is_ffmpeg_missing_error(exc: Exception) -> bool:
    if isinstance(exc, FileNotFoundError):
        return True
    message = str(exc).lower()
    return "cannot find the file" in message or "winerror 2" in message


def ffmpeg_available() -> bool:
    return shutil.which("ffprobe") is not None and shutil.which("ffmpeg") is not None


def format_exception(exc: Exception) -> str:
    message = str(exc).strip()
    if is_ffmpeg_missing_error(exc):
        return ffmpeg_missing_message()
    if message:
        return message
    return f"{type(exc).__name__}: Video processing failed. Check backend logs and ensure FFmpeg is installed."
