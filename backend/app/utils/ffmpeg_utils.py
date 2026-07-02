import os
import shutil
import sys
from pathlib import Path

_ffmpeg_path: str | None = None
_ffprobe_path: str | None = None


def _discover_binary(name: str) -> str | None:
    found = shutil.which(name)
    if found:
        return found

    local = os.environ.get("LOCALAPPDATA", "")
    if local:
        packages = Path(local) / "Microsoft" / "WinGet" / "Packages"
        if packages.is_dir():
            for candidate in packages.glob("Gyan.FFmpeg_*/**/bin/*.exe"):
                if candidate.name.lower() == f"{name.lower()}.exe":
                    return str(candidate)

    for path in (
        r"C:\ffmpeg\bin\ffmpeg.exe",
        r"C:\Program Files\ffmpeg\bin\ffmpeg.exe",
    ):
        bin_path = Path(path)
        if name == "ffprobe":
            bin_path = bin_path.with_name("ffprobe.exe")
        if bin_path.is_file():
            return str(bin_path)

    return None


def get_ffmpeg_path() -> str | None:
    global _ffmpeg_path
    if _ffmpeg_path is None:
        _ffmpeg_path = _discover_binary("ffmpeg")
    return _ffmpeg_path


def get_ffprobe_path() -> str | None:
    global _ffprobe_path
    if _ffprobe_path is None:
        _ffprobe_path = _discover_binary("ffprobe")
    return _ffprobe_path


def ensure_ffmpeg_on_path() -> None:
    """Add discovered FFmpeg bin dir to PATH so subprocess calls find ffmpeg/ffprobe."""
    ffmpeg_path = get_ffmpeg_path()
    if not ffmpeg_path:
        return
    bin_dir = str(Path(ffmpeg_path).parent)
    current = os.environ.get("PATH", "")
    if bin_dir.lower() not in current.lower():
        os.environ["PATH"] = bin_dir + os.pathsep + current


# Resolve paths as early as possible for uvicorn worker processes.
ensure_ffmpeg_on_path()


def ffmpeg_missing_message() -> str:
    if sys.platform.startswith("win"):
        install_hint = "winget install Gyan.FFmpeg"
    elif sys.platform == "darwin":
        install_hint = "brew install ffmpeg"
    else:
        install_hint = "apt-get update && apt-get install -y ffmpeg"
    return (
        "FFmpeg/ffprobe is not installed or not on PATH. "
        f"Install it with: {install_hint} — then restart the backend and click Retry."
    )


def is_ffmpeg_missing_error(exc: Exception) -> bool:
    if isinstance(exc, FileNotFoundError):
        return True
    message = str(exc).lower()
    return "cannot find the file" in message or "winerror 2" in message or "ffmpeg" in message


def ffmpeg_available() -> bool:
    return get_ffmpeg_path() is not None and get_ffprobe_path() is not None


def format_exception(exc: Exception) -> str:
    if is_ffmpeg_missing_error(exc):
        return ffmpeg_missing_message()
    message = str(exc).strip()
    if message:
        return message
    cause = getattr(exc, "__cause__", None)
    if cause and str(cause).strip():
        return f"{type(exc).__name__}: {cause}"
    return f"{type(exc).__name__}: Video processing failed. Check backend terminal logs."
