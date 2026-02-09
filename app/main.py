from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import logging
import mimetypes
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from .admin import build_admin_router
from .config import get_settings
from .db import engine, get_session, init_db
from .models import Course, Lesson, Progress
from .scan import ScanStats, scan_library


app = FastAPI(title="Udemy-Local")

templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


log = logging.getLogger(__name__)


@dataclass
class ScanMeta:
    has_scanned: bool = False
    stats: ScanStats | None = None


SCAN_META = ScanMeta()


@app.on_event("startup")
def on_startup() -> None:
    init_db()

    # Initial scan at app launch.
    # If it fails, we don't want to crash the whole app; admin can rescan.
    settings = get_settings()
    try:
        from sqlmodel import Session as _Session

        with _Session(bind=engine) as s:
            stats = scan_library(s, settings.courses_dir)
            _set_scan_meta(stats)
    except Exception:
        log.exception("initial library scan failed (courses_dir=%s)", settings.courses_dir)


def meta() -> dict[str, Any]:
    settings = get_settings()
    return {
        "courses_dir": str(settings.courses_dir),
        "scan": SCAN_META.stats,
        "has_scanned": SCAN_META.has_scanned,
    }


def _set_scan_meta(stats: ScanStats) -> None:
    SCAN_META.has_scanned = True
    SCAN_META.stats = stats


# Admin routes (manual scan, thumbnail fetch)
app.include_router(
    build_admin_router(
        templates=templates, meta_func=meta, get_session_dep=get_session, set_scan_meta=_set_scan_meta
    )
)


@app.get("/", response_class=HTMLResponse)
def home(request: Request, q: str | None = None, session: Session = Depends(get_session)):
    """Course list page."""
    m = meta()

    stmt = select(Course)
    if q:
        # Simple substring match for MVP; can upgrade to FTS later.
        stmt = stmt.where(Course.title.contains(q))
    courses = session.exec(stmt.order_by(Course.title)).all()

    return templates.TemplateResponse(request, "home.html", {"courses": courses, "q": q or "", **m})


@app.get("/course/{course_id}", response_class=HTMLResponse)
def course_detail(course_id: int, request: Request, session: Session = Depends(get_session)):
    m = meta()

    course = session.get(Course, course_id)
    if not course:
        raise HTTPException(404, "Course not found")

    lessons = session.exec(
        select(Lesson).where(Lesson.course_id == course_id).order_by(Lesson.order_key)
    ).all()

    # progress map
    lesson_ids = [l.id for l in lessons]
    prog_rows = []
    if lesson_ids:
        prog_rows = session.exec(select(Progress).where(Progress.lesson_id.in_(lesson_ids))).all()
    prog = {p.lesson_id: p for p in prog_rows}

    sections = defaultdict(list)
    for l in lessons:
        sections[l.section].append({"lesson": l, "progress": prog.get(l.id)})

    return templates.TemplateResponse(
        request,
        "course.html",
        {"course": course, "sections": dict(sections), **m},
    )


@app.get("/lesson/{lesson_id}", response_class=HTMLResponse)
def lesson_player(lesson_id: int, request: Request, session: Session = Depends(get_session)):
    m = meta()

    lesson = session.get(Lesson, lesson_id)
    if not lesson:
        raise HTTPException(404, "Lesson not found")

    course = session.get(Course, lesson.course_id)
    progress = session.exec(select(Progress).where(Progress.lesson_id == lesson_id)).first()

    return templates.TemplateResponse(
        request,
        "lesson.html",
        {"lesson": lesson, "course": course, "progress": progress, **m},
    )


@app.get("/video/{lesson_id}")
def video_stream(lesson_id: int, session: Session = Depends(get_session)):
    """Serves the underlying video file.

    FileResponse supports HTTP Range requests in Starlette, so seeking works.
    """
    lesson = session.get(Lesson, lesson_id)
    if not lesson:
        raise HTTPException(404, "Lesson not found")

    p = Path(lesson.path)
    if not p.exists() or not p.is_file():
        raise HTTPException(404, "Video file missing")

    media_type, _ = mimetypes.guess_type(p.name)
    return FileResponse(path=str(p), media_type=media_type or "application/octet-stream", filename=p.name)


class ProgressIn(BaseModel):
    position_seconds: float = Field(default=0.0, ge=0.0)
    completed: bool = False


@app.post("/api/progress/{lesson_id}")
def upsert_progress(lesson_id: int, payload: ProgressIn, session: Session = Depends(get_session)):
    lesson = session.get(Lesson, lesson_id)
    if not lesson:
        raise HTTPException(404, "Lesson not found")

    position = float(payload.position_seconds or 0.0)
    completed = bool(payload.completed)

    prog = session.exec(select(Progress).where(Progress.lesson_id == lesson_id)).first()
    if not prog:
        prog = Progress(lesson_id=lesson_id, position_seconds=position, completed=completed)
    else:
        # Don't un-complete a lesson unless explicitly asked.
        prog.position_seconds = max(0.0, position)
        if completed:
            prog.completed = True

    session.add(prog)
    session.commit()
    return {"ok": True}
