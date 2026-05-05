import asyncio

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
