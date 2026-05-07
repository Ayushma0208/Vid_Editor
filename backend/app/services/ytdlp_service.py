import asyncio
import json
from pathlib import Path

from app.config import settings


class YTDLPService:
    @staticmethod
    async def _run_yt_dlp(args: list[str]) -> tuple[int, bytes, bytes]:
        process = await asyncio.create_subprocess_exec(
            "yt-dlp",
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
