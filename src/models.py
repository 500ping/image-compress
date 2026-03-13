import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
MEDIA_DIR = os.path.join(BASE_DIR, "media")
UPLOAD_DIR = os.path.join(MEDIA_DIR, "uploads")
COMPRESSED_DIR = os.path.join(MEDIA_DIR, "compressed")
DB_DIR = os.environ.get("DB_DIR", BASE_DIR)
DB_PATH = os.path.join(DB_DIR, "compress.db")


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


@contextmanager
def get_db():
    conn = _get_conn()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    os.makedirs(COMPRESSED_DIR, exist_ok=True)
    with get_db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS files (
                id TEXT PRIMARY KEY,
                original_name TEXT NOT NULL,
                upload_filename TEXT NOT NULL,
                compressed_filename TEXT,
                original_size INTEGER,
                compressed_size INTEGER,
                quality INTEGER,
                status TEXT NOT NULL DEFAULT 'pending',
                celery_task_id TEXT,
                error TEXT,
                created_at TEXT NOT NULL
            )
        """
        )


def create_file_record(
    file_id: str,
    original_name: str,
    upload_filename: str,
    original_size: int,
    quality: int,
) -> None:
    with get_db() as conn:
        conn.execute(
            """INSERT INTO files
               (id, original_name, upload_filename, original_size, quality, status, created_at)
               VALUES (?, ?, ?, ?, ?, 'pending', ?)""",
            (
                file_id,
                original_name,
                upload_filename,
                original_size,
                quality,
                datetime.now(timezone.utc).isoformat(),
            ),
        )


def update_file_status(
    file_id: str,
    status: str,
    compressed_filename: str | None = None,
    compressed_size: int | None = None,
    celery_task_id: str | None = None,
    error: str | None = None,
) -> None:
    with get_db() as conn:
        conn.execute(
            """UPDATE files
               SET status=?, compressed_filename=COALESCE(?, compressed_filename),
                   compressed_size=COALESCE(?, compressed_size),
                   celery_task_id=COALESCE(?, celery_task_id),
                   error=COALESCE(?, error)
               WHERE id=?""",
            (
                status,
                compressed_filename,
                compressed_size,
                celery_task_id,
                error,
                file_id,
            ),
        )


def get_file(file_id: str) -> dict | None:
    with get_db() as conn:
        row = conn.execute("SELECT * FROM files WHERE id=?", (file_id,)).fetchone()
        return dict(row) if row else None


def get_all_files() -> list[dict]:
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM files ORDER BY created_at DESC").fetchall()
        return [dict(r) for r in rows]


def delete_file_record(file_id: str) -> dict | None:
    record = get_file(file_id)
    if not record:
        return None
    with get_db() as conn:
        conn.execute("DELETE FROM files WHERE id=?", (file_id,))
    return record


def delete_all_records() -> list[dict]:
    records = get_all_files()
    with get_db() as conn:
        conn.execute("DELETE FROM files")
    return records
