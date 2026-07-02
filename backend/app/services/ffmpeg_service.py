import asyncio
import json
import os
from pathlib import Path

from app.utils.ffmpeg_utils import get_ffmpeg_path, get_ffprobe_path


class FfmpegService:
    async def _run_ffmpeg(self, *args: str) -> None:
        ffmpeg_bin = get_ffmpeg_path() or "ffmpeg"
        process = await asyncio.create_subprocess_exec(
            ffmpeg_bin,
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await process.communicate()
        if process.returncode != 0:
            raise RuntimeError(stderr.decode().strip() or "FFmpeg command failed")

    async def _run_ffprobe(self, *args: str) -> bytes:
        ffprobe_bin = get_ffprobe_path() or "ffprobe"
        process = await asyncio.create_subprocess_exec(
            ffprobe_bin,
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
        if process.returncode != 0:
            raise RuntimeError(stderr.decode().strip() or "FFprobe command failed")
        return stdout

    def _part_overlay_filter(self, label: str) -> str:
        display = label.replace(" ", "-").replace("'", "").replace(":", "")
        font = os.environ.get("WINDIR", "C:\\Windows").replace("\\", "/") + "/Fonts/arialbd.ttf"
        font_arg = font.replace(":", "\\:")
        return (
            "drawbox=y=ih-72:color=0xE879A9@0.92:width=iw:height=72:t=fill,"
            f"drawtext=text='{display}':fontcolor=white:fontsize=36:fontfile='{font_arg}':"
            "x=(w-text_w)/2:y=h-48"
        )

    async def add_part_label_overlay(self, input_path: str, output_path: str, label: str) -> str:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        await self._run_ffmpeg(
            "-y",
            "-i",
            input_path,
            "-vf",
            self._part_overlay_filter(label),
            "-c:v",
            "libx264",
            "-preset",
            "fast",
            "-c:a",
            "copy",
            "-movflags",
            "+faststart",
            output_path,
        )
        return output_path

    async def transcode_to_mp4(self, input_path: str, output_path: str) -> str:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        await self._run_ffmpeg(
            "-y",
            "-i",
            input_path,
            "-c:v",
            "libx264",
            "-preset",
            "fast",
            "-c:a",
            "aac",
            "-movflags",
            "+faststart",
            output_path,
        )
        return output_path

    async def cut_clip(
        self,
        input_path: str,
        output_path: str,
        start_time: float,
        end_time: float,
        part_label: str | None = None,
    ) -> str:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        duration = max(0.1, end_time - start_time)
        work_path = output_path
        if part_label:
            work_path = str(Path(output_path).with_suffix(".work.mp4"))

        try:
            await self._run_ffmpeg(
                "-y",
                "-ss",
                str(start_time),
                "-i",
                input_path,
                "-t",
                str(duration),
                "-c",
                "copy",
                "-avoid_negative_ts",
                "make_zero",
                work_path,
            )
        except RuntimeError:
            await self._run_ffmpeg(
                "-y",
                "-ss",
                str(start_time),
                "-i",
                input_path,
                "-t",
                str(duration),
                "-c:v",
                "libx264",
                "-preset",
                "fast",
                "-c:a",
                "aac",
                "-movflags",
                "+faststart",
                work_path,
            )

        if part_label:
            await self.add_part_label_overlay(work_path, output_path, part_label)
            if work_path != output_path and Path(work_path).exists():
                Path(work_path).unlink()

        return output_path

    async def probe_duration(self, input_path: str) -> float | None:
        try:
            stdout = await self._run_ffprobe(
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                input_path,
            )
        except RuntimeError:
            return None
        try:
            return float(stdout.decode().strip())
        except ValueError:
            return None

    async def probe_dimensions(self, input_path: str) -> tuple[int, int] | None:
        try:
            stdout = await self._run_ffprobe(
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=width,height",
                "-of",
                "json",
                input_path,
            )
        except RuntimeError:
            return None
        try:
            payload = json.loads(stdout.decode() or "{}")
        except json.JSONDecodeError:
            return None
        streams = payload.get("streams") or []
        if not streams:
            return None
        stream = streams[0]
        width = stream.get("width")
        height = stream.get("height")
        if not isinstance(width, int) or not isinstance(height, int):
            return None
        return width, height

    async def resize_video(
        self,
        input_path: str,
        output_path: str,
        width: int,
        height: int,
    ) -> str:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        vf = (
            f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2"
        )
        await self._run_ffmpeg(
            "-y",
            "-i",
            input_path,
            "-vf",
            vf,
            "-c:v",
            "libx264",
            "-c:a",
            "aac",
            "-movflags",
            "+faststart",
            output_path,
        )
        return output_path

    async def create_default_ad_clip(
        self,
        output_path: str,
        width: int,
        height: int,
        duration_seconds: int,
    ) -> str:
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        process = await asyncio.create_subprocess_exec(
            get_ffmpeg_path() or "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"color=c=#111827:s={width}x{height}:d={duration_seconds}:r=30",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=880:duration={duration_seconds}:sample_rate=44100",
            "-shortest",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-movflags",
            "+faststart",
            output_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await process.communicate()
        if process.returncode != 0:
            raise RuntimeError(stderr.decode().strip() or "Default advertisement clip generation failed")
        return output_path

    async def concat_videos(self, first_path: str, second_path: str, output_path: str) -> str:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        await self._run_ffmpeg(
            "-y",
            "-i",
            first_path,
            "-i",
            second_path,
            "-filter_complex",
            "[0:v][0:a][1:v][1:a]concat=n=2:v=1:a=1[outv][outa]",
            "-map",
            "[outv]",
            "-map",
            "[outa]",
            "-c:v",
            "libx264",
            "-c:a",
            "aac",
            "-movflags",
            "+faststart",
            output_path,
        )
        return output_path
