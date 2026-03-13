import os
import uuid

from flask import (
    Flask,
    redirect,
    render_template,
    request,
    send_from_directory,
    url_for,
)

from src.models import (
    COMPRESSED_DIR,
    UPLOAD_DIR,
    create_file_record,
    delete_all_records,
    delete_file_record,
    get_all_files,
    get_files_by_ids,
    init_db,
    update_file_status,
)
from src.tasks import celery_app, compress_file

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm"}


def _remove_files(record: dict) -> None:
    upload_path = os.path.join(UPLOAD_DIR, record["upload_filename"])
    if os.path.exists(upload_path):
        os.remove(upload_path)
    if record.get("compressed_filename"):
        compressed_path = os.path.join(COMPRESSED_DIR, record["compressed_filename"])
        if os.path.exists(compressed_path):
            os.remove(compressed_path)


def create_app() -> Flask:
    app = Flask(__name__)
    init_db()

    # --------------- Pages ---------------

    @app.route("/")
    def index():
        return render_template("index.html")

    @app.route("/history")
    def history():
        files = get_all_files()
        return render_template("history.html", files=files)

    @app.route("/progress")
    def progress():
        ids = request.args.get("ids", "")
        file_ids = [fid.strip() for fid in ids.split(",") if fid.strip()]
        if not file_ids:
            return redirect(url_for("history"))

        records = get_files_by_ids(file_ids)
        all_done = True
        for r in records:
            if r["status"] in ("done", "error"):
                r["percent"] = 100 if r["status"] == "done" else 0
            elif r["celery_task_id"]:
                result = celery_app.AsyncResult(r["celery_task_id"])
                if result.state == "PROCESSING" and result.info:
                    r["percent"] = result.info.get("percent", 0)
                elif result.state == "SUCCESS":
                    r["percent"] = 100
                else:
                    r["percent"] = 0
                all_done = False
            else:
                r["percent"] = 0
                all_done = False

            if r["status"] == "done" and r["original_size"]:
                r["savings"] = round(
                    (1 - r["compressed_size"] / r["original_size"]) * 100, 1
                )

        return render_template(
            "progress.html", files=records, all_done=all_done, ids=ids
        )

    # --------------- Actions ---------------

    @app.route("/compress", methods=["POST"])
    def compress():
        files = request.files.getlist("files")
        quality = request.form.get("quality", 60, type=int)

        if not files or all(not f.filename for f in files):
            return render_template("index.html", error="No files selected.")

        file_ids = []
        for f in files:
            if not f.filename:
                continue
            ext = os.path.splitext(f.filename)[1].lower()
            if ext not in IMAGE_EXTENSIONS and ext not in VIDEO_EXTENSIONS:
                continue

            file_id = uuid.uuid4().hex
            upload_name = f"{file_id}{ext}"
            upload_path = os.path.join(UPLOAD_DIR, upload_name)
            f.save(upload_path)

            original_size = os.path.getsize(upload_path)
            create_file_record(file_id, f.filename, upload_name, original_size, quality)

            task = compress_file.delay(file_id, upload_name, quality)
            update_file_status(file_id, status="queued", celery_task_id=task.id)
            file_ids.append(file_id)

        if not file_ids:
            return render_template("index.html", error="No supported files found.")

        return redirect(url_for("progress", ids=",".join(file_ids)))

    @app.route("/delete/<file_id>", methods=["POST"])
    def delete(file_id):
        record = delete_file_record(file_id)
        if record:
            _remove_files(record)
        return redirect(url_for("history"))

    @app.route("/delete-all", methods=["POST"])
    def delete_all():
        records = delete_all_records()
        for record in records:
            _remove_files(record)
        return redirect(url_for("history"))

    @app.route("/media/compressed/<path:filename>")
    def download(filename):
        return send_from_directory(COMPRESSED_DIR, filename, as_attachment=True)

    return app
