import asyncio
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from app.utils.ffmpeg_utils import get_ffmpeg_path, get_ffprobe_path

_MEAN_VOLUME_RE = re.compile(r"mean_volume:\s*(-?\d+(?:\.\d+)?)\s*dB", re.IGNORECASE)
_MAX_VOLUME_RE = re.compile(r"max_volume:\s*(-?\d+(?:\.\d+)?)\s*dB", re.IGNORECASE)
_SCENE_SCORE_RE = re.compile(r"lavfi\.scene_score\s*=\s*([\d.]+)", re.IGNORECASE)

_drawtext_available: bool | None = None


class FfmpegService:
    def _drawtext_available(self) -> bool:
        global _drawtext_available
        if _drawtext_available is not None:
            return _drawtext_available

        ffmpeg_bin = get_ffmpeg_path() or "ffmpeg"
        try:
            result = subprocess.run(
                [ffmpeg_bin, "-filters"],
                capture_output=True,
                text=True,
                check=False,
            )
            _drawtext_available = " drawtext " in f" {result.stdout} "
        except OSError:
            _drawtext_available = False
        return _drawtext_available

    def _overlay_font_path(self) -> str | None:
        if sys.platform == "darwin":
            candidates = (
                "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
                "/Library/Fonts/Arial.ttf",
                "/System/Library/Fonts/Supplemental/Arial.ttf",
            )
        elif os.name == "nt":
            candidates = (
                os.environ.get("WINDIR", "C:\\Windows") + "\\Fonts\\arialbd.ttf",
                os.environ.get("WINDIR", "C:\\Windows") + "\\Fonts\\arial.ttf",
            )
        else:
            candidates = (
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
            )

        for candidate in candidates:
            if Path(candidate).is_file():
                return candidate
        return None

    async def _run_ffmpeg(self, *args: str, timeout: float = 240) -> None:
        ffmpeg_bin = get_ffmpeg_path() or "ffmpeg"
        process = await asyncio.create_subprocess_exec(
            ffmpeg_bin,
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            _, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
            raise RuntimeError(f"FFmpeg timed out after {int(timeout)}s")
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
        font = self._overlay_font_path()
        if font:
            font_arg = font.replace(":", "\\:")
            return (
                "drawbox=y=ih-72:color=0xE879A9@0.92:width=iw:height=72:t=fill,"
                f"drawtext=text='{display}':fontcolor=white:fontsize=36:fontfile='{font_arg}':"
                "x=(w-text_w)/2:y=h-48"
            )
        return (
            "drawbox=y=ih-72:color=0xE879A9@0.92:width=iw:height=72:t=fill,"
            f"drawtext=text='{display}':fontcolor=white:fontsize=36:"
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
            "-threads",
            "1",
            "-i",
            input_path,
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-c:a",
            "aac",
            "-ac",
            "2",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            output_path,
        )
        return output_path

    async def compress_under_bytes(self, input_path: str, output_path: str, max_bytes: int) -> str:
        """Re-encode so the file fits Cloudinary's typical 100MB video cap."""
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        duration = await self.probe_duration(input_path) or 0
        audio_bps = 96_000
        if duration > 1:
            video_bps = int((max_bytes * 8 * 0.82) / duration) - audio_bps
            video_k = max(250, video_bps // 1000)
        else:
            video_k = 800

        attempts: list[tuple[int, str | None]] = [
            (video_k, None),
            (max(250, video_k * 2 // 3), "scale=-2:720"),
            (max(200, video_k // 2), "scale=-2:480"),
        ]
        last_error: Exception | None = None
        for bitrate_k, scale in attempts:
            args = [
                "-y",
                "-threads",
                "1",
                "-i",
                input_path,
                "-c:v",
                "libx264",
                "-preset",
                "ultrafast",
                "-b:v",
                f"{bitrate_k}k",
                "-maxrate",
                f"{bitrate_k}k",
                "-bufsize",
                f"{bitrate_k * 2}k",
                "-c:a",
                "aac",
                "-b:a",
                "96k",
                "-ac",
                "2",
                "-pix_fmt",
                "yuv420p",
                "-movflags",
                "+faststart",
            ]
            if scale:
                args.extend(["-vf", scale])
            args.append(output_path)
            try:
                await self._run_ffmpeg(*args)
            except Exception as exc:
                last_error = exc
                continue
            if Path(output_path).is_file() and Path(output_path).stat().st_size <= max_bytes:
                return output_path

        size = Path(output_path).stat().st_size if Path(output_path).is_file() else 0
        raise RuntimeError(
            f"Could not compress video under {max_bytes} bytes (got {size})"
            + (f": {last_error}" if last_error else "")
        )

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
                "-threads",
                "1",
                "-ss",
                str(start_time),
                "-i",
                input_path,
                "-t",
                str(duration),
                "-c:v",
                "libx264",
                "-preset",
                "ultrafast",
                "-c:a",
                "aac",
                "-movflags",
                "+faststart",
                work_path,
            )

        if part_label:
            if self._drawtext_available():
                await self.add_part_label_overlay(work_path, output_path, part_label)
                if work_path != output_path and Path(work_path).exists():
                    Path(work_path).unlink()
            else:
                shutil.move(work_path, output_path)

        return output_path

    async def extract_audio_segment(
        self,
        input_path: str,
        output_path: str,
        start_time: float = 0.0,
        duration_seconds: float = 300.0,
    ) -> str:
        """Extract a mono MP3 audio sample for transcription / summarization."""
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        await self._run_ffmpeg(
            "-y",
            "-ss",
            str(max(0.0, start_time)),
            "-t",
            str(max(1.0, duration_seconds)),
            "-i",
            input_path,
            "-vn",
            "-acodec",
            "libmp3lame",
            "-ar",
            "16000",
            "-ac",
            "1",
            "-b:a",
            "64k",
            output_path,
        )
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

    async def probe_volume_stats(self, input_path: str) -> dict[str, float] | None:
        """Return mean_volume / max_volume in dB via volumedetect, or None on failure."""
        ffmpeg_bin = get_ffmpeg_path() or "ffmpeg"
        process = await asyncio.create_subprocess_exec(
            ffmpeg_bin,
            "-hide_banner",
            "-i",
            input_path,
            "-vn",
            "-af",
            "volumedetect",
            "-f",
            "null",
            "-",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await process.communicate()
        text = stderr.decode(errors="replace") if stderr else ""
        mean_match = _MEAN_VOLUME_RE.search(text)
        max_match = _MAX_VOLUME_RE.search(text)
        if not mean_match and not max_match:
            return None
        result: dict[str, float] = {}
        if mean_match:
            result["mean_volume"] = float(mean_match.group(1))
        if max_match:
            result["max_volume"] = float(max_match.group(1))
        return result or None

    async def probe_scene_change_count(self, input_path: str, threshold: float = 0.3) -> int | None:
        """Count frames where scene score exceeds threshold. Returns None on failure."""
        safe_threshold = max(0.01, min(1.0, float(threshold)))
        ffmpeg_bin = get_ffmpeg_path() or "ffmpeg"
        process = await asyncio.create_subprocess_exec(
            ffmpeg_bin,
            "-hide_banner",
            "-i",
            input_path,
            "-vf",
            f"select='gt(scene\\,{safe_threshold})',showinfo",
            "-an",
            "-f",
            "null",
            "-",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await process.communicate()
        text = stderr.decode(errors="replace") if stderr else ""
        if not text.strip():
            return None

        scene_hits = _SCENE_SCORE_RE.findall(text)
        if scene_hits:
            return len(scene_hits)

        showinfo_lines = [
            line for line in text.splitlines() if "Parsed_showinfo" in line or "showinfo" in line.lower()
        ]
        if showinfo_lines:
            return len(showinfo_lines)

        n_lines = [line for line in text.splitlines() if re.search(r"\bn:\s*\d+", line)]
        if n_lines:
            return len(n_lines)

        # Successful run with zero scene changes is a valid 0.
        if process.returncode == 0:
            return 0
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

    async def scale_to_height(self, input_path: str, output_path: str, height: int) -> str:
        """Downscale (or copy-scale) preserving aspect ratio; width is even for H.264."""
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        target = max(2, int(height))
        await self._run_ffmpeg(
            "-y",
            "-i",
            input_path,
            "-vf",
            f"scale=-2:{target}",
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
