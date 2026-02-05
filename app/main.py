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
from .db import get_session, init_db
from .models import Course, Lesson, Progress
from .scan import scan_library


app = FastAPI(title="Udemy-Local")

templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


@app.on_event("startup")
def on_startup():
    init_db()


def ensure_scanned(session: Session) -> dict[str, Any]:
    settings = get_settings()
    stats = scan_library(session, settings.courses_dir)
    return {"courses_dir": str(settings.courses_dir), "scan": stats}


@app.get("/", response_class=HTMLResponse)
def home(request: Request, session: Session = Depends(get_session)):
    meta = ensure_scanned(session)

    courses = session.exec(select(Course).order_by(Course.title)).all()
    return templates.TemplateResponse(
        request,
        "home.html",
        {"courses": courses, **meta},
    )


@app.get("/course/{course_id}", response_class=HTMLResponse)
def course_detail(course_id: int, request: Request, session: Session = Depends(get_session)):
    meta = ensure_scanned(session)

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
        {"course": course, "sections": dict(sections), **meta},
    )


@app.get("/lesson/{lesson_id}", response_class=HTMLResponse)
def lesson_player(lesson_id: int, request: Request, session: Session = Depends(get_session)):
    meta = ensure_scanned(session)

    lesson = session.get(Lesson, lesson_id)
    if not lesson:
        raise HTTPException(404, "Lesson not found")

    course = session.get(Course, lesson.course_id)
    progress = session.exec(select(Progress).where(Progress.lesson_id == lesson_id)).first()

    return templates.TemplateResponse(
        request,
        "lesson.html",
        {"lesson": lesson, "course": course, "progress": progress, **meta},
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
