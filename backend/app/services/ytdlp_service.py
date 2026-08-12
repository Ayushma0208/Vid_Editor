import asyncio
import json
import sys
from pathlib import Path

from app.config import settings


class YTDLPService:
    @staticmethod
    async def _run_yt_dlp(args: list[str]) -> tuple[int, bytes, bytes]:
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "yt_dlp",
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
        return process.returncode, stdout, stderr

    @staticmethod
    def _friendly_error(stderr_text: str) -> str:
        lowered = stderr_text.lower()
        if "precondition check failed" in lowered or "nsig extraction failed" in lowered or "http error 403" in lowered:
            return (
                "YouTube blocked the current extraction path (403/nsig/precondition). "
                "Try again in a bit, or use a different video URL. "
                f"Raw yt-dlp error: {stderr_text}"
            )
        return stderr_text or "yt-dlp download failed"

    @staticmethod
    def _cookie_args() -> list[str]:
        cookie_file = (settings.yt_dlp_cookies_file or "").strip()
        if cookie_file:
            return ["--cookies", cookie_file]
        return []

    async def get_metadata(self, url: str) -> dict:
        client_attempts = [
            "youtube:player_client=android,web",
            "youtube:player_client=ios,android",
            "youtube:player_client=tv_embedded,android",
        ]
        base_args = [
            "--no-playlist",
            "--retries",
            "3",
            "--socket-timeout",
            "20",
            "--dump-json",
            "--no-download",
        ]
        cookie_args = self._cookie_args()
        stdout = b""
        stderr = b""
        best_stderr = ""
        return_code = 1
        for client_args in client_attempts:
            return_code, stdout, stderr = await self._run_yt_dlp(
                cookie_args + base_args + ["--extractor-args", client_args, url]
            )
            if return_code == 0:
                break
            err_text = stderr.decode().strip()
            if err_text:
                best_stderr = err_text
        if return_code != 0:
            raise RuntimeError(self._friendly_error(best_stderr or stderr.decode().strip()))

        output = stdout.decode().strip()
        if not output:
            raise RuntimeError("yt-dlp returned empty metadata response")

        try:
            return json.loads(output.splitlines()[0])
        except (IndexError, json.JSONDecodeError) as exc:
            raise RuntimeError("Failed to parse yt-dlp metadata JSON") from exc

    async def list_available_heights(self, url: str) -> set[int]:
        """Return distinct video heights available for the URL (from format metadata)."""
        metadata = await self.get_metadata(url)
        heights: set[int] = set()
        for fmt in metadata.get("formats") or []:
            height = fmt.get("height")
            if isinstance(height, int) and height > 0:
                heights.add(height)
            elif isinstance(height, float) and height > 0:
                heights.add(int(height))
        # Some extractors only expose requested/best height on the top-level entry.
        top_height = metadata.get("height")
        if isinstance(top_height, int) and top_height > 0:
            heights.add(top_height)
        return heights

    def _height_available(self, available: set[int], target_height: int) -> bool:
        """True if an exact height exists, or a format within a small tolerance band."""
        if target_height in available:
            return True
        # Allow near-matches (e.g. 242≈240, 478≈480) but do not nearest-up to another bucket.
        tolerance = 15
        return any(abs(h - target_height) <= tolerance for h in available)

    async def download_video_quality(self, url: str, output_path: str, height: int) -> str:
        """Download a specific target height. Raises if download fails."""
        output_target = Path(output_path)
        output_target.parent.mkdir(parents=True, exist_ok=True)
        # Prefer exact height; fall back to height<=target within the same ladder step only
        # when exact is unavailable at download time (list check already skipped missing).
        fmt = (
            f"bestvideo[height={height}]+bestaudio/"
            f"best[height={height}]/"
            f"bestvideo[height<={height}][height>={max(1, height - 15)}]+bestaudio/"
            f"best[height<={height}][height>={max(1, height - 15)}]"
        )
        client_attempts = [
            "youtube:player_client=android,web",
            "youtube:player_client=ios,android",
            "youtube:player_client=tv_embedded,android",
        ]
        cmd_common = [
            "--no-playlist",
            "--retries",
            "5",
            "--fragment-retries",
            "5",
            "--socket-timeout",
            "20",
            "--force-ipv4",
            "--merge-output-format",
            "mp4",
            "--print",
            "after_move:filepath",
            "-o",
            str(output_target),
        ]
        cookie_args = self._cookie_args()
        stdout = b""
        stderr = b""
        best_stderr = ""
        return_code = 1
        for client_args in client_attempts:
            return_code, stdout, stderr = await self._run_yt_dlp(
                cookie_args + cmd_common + ["--extractor-args", client_args, "-f", fmt, url]
            )
            if return_code == 0:
                break
            err_text = stderr.decode().strip()
            if err_text:
                best_stderr = err_text
        if return_code != 0:
            raise RuntimeError(self._friendly_error(best_stderr or stderr.decode().strip()))

        printed = [line.strip() for line in stdout.decode().splitlines() if line.strip()]
        if printed:
            return printed[-1]
        if output_target.exists():
            return str(output_target)
        # yt-dlp may write with a real extension replacing %(ext)s
        matches = list(output_target.parent.glob(output_target.stem + ".*"))
        if matches:
            return str(matches[0])
        raise RuntimeError(f"yt-dlp completed but {height}p output was not detected")

    async def download_video(self, url: str, output_path: str, quality: str = "1080p") -> str:
        height = "".join(ch for ch in quality if ch.isdigit()) or "1080"
        output_target = Path(output_path)
        output_target.parent.mkdir(parents=True, exist_ok=True)
        client_attempts = [
            "youtube:player_client=android,web",
            "youtube:player_client=ios,android",
            "youtube:player_client=tv_embedded,android",
        ]
        cmd_common = [
            "--no-playlist",
            "--retries",
            "5",
            "--fragment-retries",
            "5",
            "--socket-timeout",
            "20",
            "--force-ipv4",
            "--merge-output-format",
            "mp4",
            "--print",
            "after_move:filepath",
            "-o",
            str(output_target),
        ]
        cookie_args = self._cookie_args()
        format_attempts = [
            f"bestvideo[height<={height}]+bestaudio/best",
            "best[ext=mp4]/best",
        ]
        stdout = b""
        stderr = b""
        best_stderr = ""
        return_code = 1
        for client_args in client_attempts:
            for fmt in format_attempts:
                return_code, stdout, stderr = await self._run_yt_dlp(
                    cookie_args + cmd_common + ["--extractor-args", client_args, "-f", fmt, url]
                )
                if return_code == 0:
                    break
                err_text = stderr.decode().strip()
                if err_text:
                    best_stderr = err_text
            if return_code == 0:
                break
        if return_code != 0:
            raise RuntimeError(self._friendly_error(best_stderr or stderr.decode().strip()))

        printed = [line.strip() for line in stdout.decode().splitlines() if line.strip()]
        if printed:
            return printed[-1]

        # Fallback for older yt-dlp output behavior.
        if output_target.exists():
            return str(output_target)

        raise RuntimeError("yt-dlp completed but output file path was not detected")
