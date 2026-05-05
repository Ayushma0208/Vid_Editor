from app.workers.celery_app import celery_app

PIPELINE_STEPS = [
    ("downloading",   10, "app.workers.downloader.download_video"),
    ("transcribing",  25, "app.workers.transcriber.transcribe_video"),
    ("analyzing",     45, "app.workers.clip_selector.select_clips"),
    ("cutting",       60, "app.workers.video_processor.process_clips"),
    ("captioning",    75, "app.workers.caption_burner.burn_captions"),
    ("scoring",       88, "app.workers.viral_scorer.score_clips"),
    ("broll",         95, "app.workers.broll_fetcher.fetch_broll"),
]

@celery_app.task(bind=True, name="app.workers.pipeline.run_pipeline")
def run_pipeline(self, job_id: str):
    import asyncio
    from app.workers._helpers import update_job_status, emit_progress

    for status, progress, task_path in PIPELINE_STEPS:
        try:
            asyncio.run(update_job_status(job_id, status, progress))
            asyncio.run(emit_progress(job_id, status, progress))

            module_path, func_name = task_path.rsplit(".", 1)
            import importlib
            mod = importlib.import_module(module_path)
            func = getattr(mod, func_name)
            func(job_id)

        except Exception as e:
            asyncio.run(update_job_status(job_id, "failed", 0, str(e)))
            asyncio.run(emit_progress(job_id, "failed", 0))
            raise

    asyncio.run(update_job_status(job_id, "done", 100))
    asyncio.run(emit_progress(job_id, "done", 100))
    return {"job_id": job_id, "status": "done"}
