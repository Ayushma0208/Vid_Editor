import asyncio
import json
from pathlib import Path

import ffmpeg


class FfmpegService:
    async def cut_clip(
        self,
        input_path: str,
        output_path: str,
        start_time: float,
        end_time: float,
    ) -> str:
        stream = ffmpeg.input(input_path, ss=start_time, to=end_time)

        # First attempt stream copy for speed.
        copy_graph = ffmpeg.output(
            stream,
            output_path,
            c="copy",
            avoid_negative_ts="make_zero",
        ).overwrite_output()

        try:
            await asyncio.to_thread(ffmpeg.run, copy_graph, capture_stdout=True, capture_stderr=True)
        except ffmpeg.Error:
            # Fall back to re-encode when copy cut is not possible.
            reencode_graph = ffmpeg.output(
                stream,
                output_path,
                vcodec="libx264",
                acodec="aac",
                movflags="+faststart",
                avoid_negative_ts="make_zero",
            ).overwrite_output()
            await asyncio.to_thread(ffmpeg.run, reencode_graph, capture_stdout=True, capture_stderr=True)

        return output_path

    async def probe_duration(self, input_path: str) -> float | None:
        process = await asyncio.create_subprocess_exec(
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            input_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await process.communicate()
        if process.returncode != 0:
            return None
        try:
            return float(stdout.decode().strip())
        except ValueError:
            return None

    async def probe_dimensions(self, input_path: str) -> tuple[int, int] | None:
        process = await asyncio.create_subprocess_exec(
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height",
            "-of",
            "json",
            input_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await process.communicate()
        if process.returncode != 0:
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
        stream = ffmpeg.input(input_path)
        video = stream.video.filter(
            "scale",
            width,
            height,
            force_original_aspect_ratio="decrease",
        ).filter("pad", width, height, "(ow-iw)/2", "(oh-ih)/2")
        output_graph = ffmpeg.output(
            video,
            stream.audio,
            output_path,
            vcodec="libx264",
            acodec="aac",
            movflags="+faststart",
        ).overwrite_output()
        await asyncio.to_thread(ffmpeg.run, output_graph, capture_stdout=True, capture_stderr=True)
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
            "ffmpeg",
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
        first = ffmpeg.input(first_path)
        second = ffmpeg.input(second_path)
        concat_graph = ffmpeg.concat(
            first.video,
            first.audio,
            second.video,
            second.audio,
            v=1,
            a=1,
        )
        output_graph = ffmpeg.output(
            concat_graph[0],
            concat_graph[1],
            output_path,
            vcodec="libx264",
            acodec="aac",
            movflags="+faststart",
        ).overwrite_output()
        await asyncio.to_thread(ffmpeg.run, output_graph, capture_stdout=True, capture_stderr=True)
        return output_path
