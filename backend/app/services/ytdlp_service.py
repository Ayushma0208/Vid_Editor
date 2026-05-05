import asyncio
import json
from pathlib import Path


class YTDLPService:
    async def get_metadata(self, url: str) -> dict:
        process = await asyncio.create_subprocess_exec(
            "yt-dlp",
            "--dump-json",
            "--no-download",
            "--no-playlist",
            url,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
        if process.returncode != 0:
            raise RuntimeError(stderr.decode().strip() or "yt-dlp metadata extraction failed")

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

        process = await asyncio.create_subprocess_exec(
            "yt-dlp",
            "--no-playlist",
            "-f",
            f"bestvideo[height<={height}]+bestaudio/best",
            "--merge-output-format",
            "mp4",
            "--print",
            "after_move:filepath",
            "-o",
            str(output_target),
            url,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
        if process.returncode != 0:
            raise RuntimeError(stderr.decode().strip() or "yt-dlp download failed")

        printed = [line.strip() for line in stdout.decode().splitlines() if line.strip()]
        if printed:
            return printed[-1]

        # Fallback for older yt-dlp output behavior.
        if output_target.exists():
            return str(output_target)

        raise RuntimeError("yt-dlp completed but output file path was not detected")
