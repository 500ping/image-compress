# CompressIt

A web application for compressing images and videos, built with Flask and Celery.

## Features

- Upload and compress multiple images and videos at once
- Background processing with Celery (4 parallel workers)
- Real-time progress tracking in the UI
- Compression history page with download links
- Delete individual files or all files at once
- Supports images (JPG, PNG, WebP, BMP, TIFF) and videos (MP4, MOV, AVI, MKV, WebM)

## Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) (package manager)
- [ffmpeg](https://ffmpeg.org/) (for video compression)

Install ffmpeg on macOS:

```bash
brew install ffmpeg
```

## Installation

```bash
# Clone the repository
git clone <repo-url>
cd compress-demo

# Install dependencies
uv sync
```

## Usage

You need to run two processes:

**Terminal 1 - Celery worker:**

```bash
uv run celery -A src.tasks.celery_app worker --loglevel=info --concurrency=4
```

**Terminal 2 - Flask app:**

```bash
uv run python main.py
```

Open http://localhost:5000 in your browser.

### Docker

```bash
docker compose up --build
```

Open http://localhost:5000 in your browser.

## Project Structure

```
compress-demo/
├── main.py                  # App entry point
├── src/
│   ├── app.py               # Flask routes
│   ├── models.py            # SQLite database layer
│   ├── tasks.py             # Celery background tasks
│   └── templates/
│       ├── base.html        # Shared layout
│       ├── index.html       # Upload & compress page
│       └── history.html     # Compression history page
├── media/
│   ├── uploads/             # Original uploaded files
│   └── compressed/          # Compressed output files
├── pyproject.toml
└── uv.lock
```
