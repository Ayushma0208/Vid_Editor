import os
import platform
import shutil
import sys
import tarfile
import tempfile
import threading
import urllib.request
from pathlib import Path

_ffmpeg_path: str | None = None
_ffprobe_path: str | None = None
_install_lock = threading.Lock()
_STATIC_URLS = {
    "x86_64": "https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz",
    "amd64": "https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz",
    "aarch64": "https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-arm64-static.tar.xz",
    "arm64": "https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-arm64-static.tar.xz",
}


def _bin_dir() -> Path:
    root = Path(os.environ.get("TEMP_DIR") or "/tmp/videoedit")
    path = root / "bin"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _discover_binary(name: str) -> str | None:
    found = shutil.which(name)
    if found:
        return found

    bundled = _bin_dir() / name
    if bundled.is_file() and os.access(bundled, os.X_OK):
        return str(bundled)

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


def _install_static_ffmpeg() -> None:
    if not sys.platform.startswith("linux"):
        return
    dest = _bin_dir()
    ffmpeg_bin = dest / "ffmpeg"
    ffprobe_bin = dest / "ffprobe"
    if ffmpeg_bin.is_file() and ffprobe_bin.is_file() and os.access(ffmpeg_bin, os.X_OK):
        _prepend_path(dest)
        return

    url = _STATIC_URLS.get(platform.machine().lower())
    if not url:
        print(f"[ffmpeg] No static build URL for arch={platform.machine()}", flush=True)
        return

    print(f"[ffmpeg] Downloading static FFmpeg from {url}", flush=True)
    try:
        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp) / "ffmpeg.tar.xz"
            urllib.request.urlretrieve(url, archive)
            with tarfile.open(archive, "r:xz") as tar:
                tar.extractall(tmp)
            extracted_ffmpeg = next(Path(tmp).rglob("ffmpeg"), None)
            extracted_ffprobe = next(Path(tmp).rglob("ffprobe"), None)
            if not extracted_ffmpeg or not extracted_ffprobe:
                raise RuntimeError("Static archive did not contain ffmpeg/ffprobe")
            shutil.copy2(extracted_ffmpeg, ffmpeg_bin)
            shutil.copy2(extracted_ffprobe, ffprobe_bin)
            ffmpeg_bin.chmod(0o755)
            ffprobe_bin.chmod(0o755)
        _prepend_path(dest)
        print(f"[ffmpeg] Installed static binaries in {dest}", flush=True)
    except Exception as exc:
        print(f"[ffmpeg] Static install failed: {exc}", flush=True)


def _prepend_path(bin_dir: Path) -> None:
    current = os.environ.get("PATH", "")
    prefix = str(bin_dir)
    if prefix.lower() not in current.lower():
        os.environ["PATH"] = prefix + os.pathsep + current


def get_ffmpeg_path() -> str | None:
    global _ffmpeg_path
    if _ffmpeg_path:
        return _ffmpeg_path
    found = _discover_binary("ffmpeg")
    if not found:
        with _install_lock:
            found = _discover_binary("ffmpeg")
            if not found:
                _install_static_ffmpeg()
                found = _discover_binary("ffmpeg")
    _ffmpeg_path = found
    return _ffmpeg_path


def get_ffprobe_path() -> str | None:
    global _ffprobe_path
    if _ffprobe_path:
        return _ffprobe_path
    found = _discover_binary("ffprobe")
    if not found:
        get_ffmpeg_path()
        found = _discover_binary("ffprobe")
    _ffprobe_path = found
    return _ffprobe_path


def ensure_ffmpeg_on_path() -> None:
    """Add FFmpeg to PATH, downloading a static Linux build when apt/Docker did not install it."""
    ffmpeg_path = get_ffmpeg_path()
    probe_path = get_ffprobe_path()
    for binary in (ffmpeg_path, probe_path):
        if not binary:
            continue
        _prepend_path(Path(binary).parent)


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
