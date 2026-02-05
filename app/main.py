from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.responses import FileResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select

from .config import get_settings
from .db import get_session, init_db, engine
from .models import Course, Lesson, Progress
from .scan import scan_library
from .admin import build_admin_router
from .udemy_thumb import best_thumbnail_for_course_title


app = FastAPI(title="Udemy-Local")

templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


SCAN_META: dict[str, Any] = {"has_scanned": False, "scan": None}


@app.on_event("startup")
def on_startup():
    init_db()

    # Initial scan at app launch.
    settings = get_settings()
    from sqlmodel import Session as _Session

    with _Session(bind=engine) as s:
        stats = scan_library(s, settings.courses_dir)
        SCAN_META["has_scanned"] = True
        SCAN_META["scan"] = stats


def session_engine():
    return engine


def meta() -> dict[str, Any]:
    settings = get_settings()
    return {
        "courses_dir": str(settings.courses_dir),
        "scan": SCAN_META.get("scan"),
        "has_scanned": bool(SCAN_META.get("has_scanned")),
    }


def _set_scan_meta(stats):
    SCAN_META["has_scanned"] = True
    SCAN_META["scan"] = stats


# Admin routes (manual scan, thumbnail fetch)
app.include_router(
    build_admin_router(
        templates=templates, meta_func=meta, get_session_dep=get_session, set_scan_meta=_set_scan_meta
    )
)


@app.get("/", response_class=HTMLResponse)
def home(request: Request, q: str | None = None, session: Session = Depends(get_session)):
    m = meta()

    stmt = select(Course)
    if q:
        stmt = stmt.where(Course.title.contains(q))
    courses = session.exec(stmt.order_by(Course.title)).all()

    return templates.TemplateResponse(
        request,
        "home.html",
        {"courses": courses, "q": q or "", **m},
    )


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
    lesson = session.get(Lesson, lesson_id)
    if not lesson:
        raise HTTPException(404, "Lesson not found")

    p = Path(lesson.path)
    if not p.exists() or not p.is_file():
        raise HTTPException(404, "Video file missing")

    # FileResponse supports Range requests in Starlette; good for seeking.
    return FileResponse(path=str(p), media_type="video/mp4", filename=p.name)


@app.post("/api/progress/{lesson_id}")
def upsert_progress(lesson_id: int, payload: dict, session: Session = Depends(get_session)):
    lesson = session.get(Lesson, lesson_id)
    if not lesson:
        raise HTTPException(404, "Lesson not found")

    position = float(payload.get("position_seconds", 0.0) or 0.0)
    completed = bool(payload.get("completed", False))

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
