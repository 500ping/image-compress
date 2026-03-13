import os
import uuid

from flask import (
    Flask,
    jsonify,
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
    get_file,
    init_db,
    update_file_status,
)
from src.tasks import celery_app, compress_file

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm"}


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

    # --------------- API ---------------

    @app.route("/compress", methods=["POST"])
    def compress():
        files = request.files.getlist("files")
        quality = request.form.get("quality", 60, type=int)

        if not files or all(not f.filename for f in files):
            return jsonify({"error": "No files selected."}), 400

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

        return jsonify({"file_ids": file_ids})

    @app.route("/progress/<file_id>")
    def progress(file_id):
        record = get_file(file_id)
        if not record:
            return jsonify({"error": "Not found"}), 404

        percent = 0
        if record["status"] == "done":
            percent = 100
        elif record["status"] == "error":
            return jsonify(
                {
                    "file_id": file_id,
                    "status": "error",
                    "percent": 0,
                    "error": record.get("error", "Unknown error"),
                    "original_name": record["original_name"],
                }
            )
        elif record["celery_task_id"]:
            result = celery_app.AsyncResult(record["celery_task_id"])
            if result.state == "PROCESSING" and result.info:
                percent = result.info.get("percent", 0)
            elif result.state == "SUCCESS":
                percent = 100

        resp = {
            "file_id": file_id,
            "status": record["status"],
            "percent": percent,
            "original_name": record["original_name"],
            "original_size": record["original_size"],
        }
        if record["status"] == "done":
            resp["compressed_size"] = record["compressed_size"]
            resp["compressed_filename"] = record["compressed_filename"]
            savings = round(
                (1 - record["compressed_size"] / record["original_size"]) * 100, 1
            )
            resp["savings"] = savings
        return jsonify(resp)

    @app.route("/delete/<file_id>", methods=["POST"])
    def delete(file_id):
        record = delete_file_record(file_id)
        if not record:
            return jsonify({"error": "Not found"}), 404

        # Remove uploaded file
        upload_path = os.path.join(UPLOAD_DIR, record["upload_filename"])
        if os.path.exists(upload_path):
            os.remove(upload_path)

        # Remove compressed file
        if record.get("compressed_filename"):
            compressed_path = os.path.join(
                COMPRESSED_DIR, record["compressed_filename"]
            )
            if os.path.exists(compressed_path):
                os.remove(compressed_path)

        if request.headers.get("Accept") == "application/json":
            return jsonify({"ok": True})
        return redirect(url_for("history"))

    @app.route("/delete-all", methods=["POST"])
    def delete_all():
        records = delete_all_records()
        for record in records:
            upload_path = os.path.join(UPLOAD_DIR, record["upload_filename"])
            if os.path.exists(upload_path):
                os.remove(upload_path)
            if record.get("compressed_filename"):
                compressed_path = os.path.join(
                    COMPRESSED_DIR, record["compressed_filename"]
                )
                if os.path.exists(compressed_path):
                    os.remove(compressed_path)

        if request.headers.get("Accept") == "application/json":
            return jsonify({"ok": True})
        return redirect(url_for("history"))

    @app.route("/media/compressed/<path:filename>")
    def download(filename):
        return send_from_directory(COMPRESSED_DIR, filename, as_attachment=True)

    return app
