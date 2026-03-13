import os

import ffmpeg
from celery import Celery
from PIL import Image

from src.models import COMPRESSED_DIR, UPLOAD_DIR, update_file_status

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
BROKER_DB = os.path.join(BASE_DIR, "celery_broker.db")
BACKEND_DB = os.path.join(BASE_DIR, "celery_results.db")

celery_app = Celery(
    "compress_demo",
    broker=f"sqla+sqlite:///{BROKER_DB}",
    backend=f"db+sqlite:///{BACKEND_DB}",
)
celery_app.conf.worker_concurrency = 4
celery_app.conf.task_acks_late = True
celery_app.conf.broker_connection_retry_on_startup = True

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm"}


@celery_app.task(bind=True)
def compress_file(self, file_id: str, upload_filename: str, quality: int) -> dict:
    upload_path = os.path.join(UPLOAD_DIR, upload_filename)
    ext = os.path.splitext(upload_filename)[1].lower()

    compressed_name = os.path.splitext(upload_filename)[0] + (
        ".jpg" if ext in IMAGE_EXTENSIONS else ext
    )
    compressed_path = os.path.join(COMPRESSED_DIR, compressed_name)

    update_file_status(file_id, status="processing", celery_task_id=self.request.id)
    self.update_state(state="PROCESSING", meta={"file_id": file_id, "percent": 0})

    try:
        if ext in IMAGE_EXTENSIONS:
            self.update_state(
                state="PROCESSING", meta={"file_id": file_id, "percent": 30}
            )
            img = Image.open(upload_path)
            img = img.convert("RGB") if img.mode in ("RGBA", "P") else img
            img.save(compressed_path, "JPEG", quality=quality, optimize=True)
            self.update_state(
                state="PROCESSING", meta={"file_id": file_id, "percent": 90}
            )
        else:
            self.update_state(
                state="PROCESSING", meta={"file_id": file_id, "percent": 10}
            )
            ffmpeg.input(upload_path).output(
                compressed_path,
                vcodec="libx264",
                crf=quality,
                preset="medium",
                acodec="aac",
                audio_bitrate="128k",
            ).overwrite_output().run(quiet=True)
            self.update_state(
                state="PROCESSING", meta={"file_id": file_id, "percent": 90}
            )

        compressed_size = os.path.getsize(compressed_path)
        update_file_status(
            file_id,
            status="done",
            compressed_filename=compressed_name,
            compressed_size=compressed_size,
        )
        self.update_state(state="DONE", meta={"file_id": file_id, "percent": 100})
        return {"file_id": file_id, "status": "done", "percent": 100}

    except Exception as e:
        update_file_status(file_id, status="error", error=str(e))
        self.update_state(
            state="FAILURE", meta={"file_id": file_id, "percent": 0, "error": str(e)}
        )
        raise
