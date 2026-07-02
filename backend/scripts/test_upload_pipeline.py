"""Create a tiny test video and run the upload pipeline to capture the real error."""
import asyncio
import traceback
from pathlib import Path

from app.config import settings
from app.database import init_db
from app.models.project import Project, ProjectStatus
from app.tasks.upload_task import _run_upload_pipeline, staging_upload_path
from app.utils.ffmpeg_utils import get_ffmpeg_path


async def create_sample_video(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg = get_ffmpeg_path() or "ffmpeg"
    process = await asyncio.create_subprocess_exec(
        ffmpeg,
        "-y",
        "-f",
        "lavfi",
        "-i",
        "color=c=blue:s=640x360:d=10",
        "-f",
        "lavfi",
        "-i",
        "sine=f=440:d=10",
        "-shortest",
        "-c:v",
        "libx264",
        "-c:a",
        "aac",
        str(path),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await process.communicate()
    if process.returncode != 0:
        raise RuntimeError(stderr.decode())


async def main() -> None:
    await init_db()
    user_id = "test-user"
    sample = Path(settings.temp_dir) / "uploads" / f"{user_id}-sample.mp4"
    print("temp_dir:", settings.temp_dir)
    print("creating sample:", sample)
    await create_sample_video(sample)

    project = Project(
        user_id=user_id,
        title="Pipeline test",
        yt_url="upload://sample",
        yt_video_id="pending",
        status=ProjectStatus.PENDING,
        cloudinary_folder="projects/uploads/",
        metadata={"source": "upload", "original_filename": "sample.mp4"},
    )
    await project.insert()
    project.yt_video_id = f"upload-{project.id}"
    await project.save()
    pid = str(project.id)
    print("project_id:", pid)

    try:
        result = await _run_upload_pipeline(pid, sample)
        print("SUCCESS:", result)
    except Exception as exc:
        print("FAILED:", type(exc).__name__, exc)
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
