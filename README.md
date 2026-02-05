# Udemy-Local (FastAPI)

Self-hosted course library UI (Udemy-ish) for locally saved course folders/videos.

## Features (MVP)
- Scans a courses directory on each page load (simple + reliable).
- Clean UI: courses list → course detail (sections/lessons) → video player.
- Progress tracking (single-user) in SQLite.

## Assumptions about your folder layout
- `COURSES_DIR/`
  - `Some Course Title/`
    - `01 Section Name/`
      - `01 Lesson title.mp4`
      - `02 Another lesson.mkv`
    - `02 Another Section/`...

Files are ordered by natural sort of folder/file names.

## Running
This repo doesn’t include a venv yet because this machine is missing `python3-venv`.

On Ubuntu/Debian:

```bash
sudo apt install python3.12-venv
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt

export COURSES_DIR=/path/to/courses
uvicorn app.main:app --reload --port 8000
```

Open: http://localhost:8000

## Config
- `COURSES_DIR` (required): root directory containing course folders
- `DATABASE_URL` (optional): default `sqlite:///./udemy_local.db`
