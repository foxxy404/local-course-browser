from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from sqlmodel import Session, select

from .models import Course, Lesson


VIDEO_EXTS = {".mp4", ".mkv", ".webm", ".mov", ".m4v"}


def natural_key(s: str):
    # Split into [text|int] chunks so 2 < 10.
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", s)]


@dataclass
class ScanStats:
    courses_seen: int = 0
    lessons_seen: int = 0


def iter_video_files(course_dir: Path) -> Iterable[tuple[str, Path]]:
    # Expect: course_dir/section_dir/video_file
    # Also tolerate deeper nesting: we keep section as immediate parent folder name.
    for p in sorted(course_dir.rglob("*"), key=lambda x: natural_key(str(x))):
        if not p.is_file():
            continue
        if p.suffix.lower() not in VIDEO_EXTS:
            continue
        section = p.parent.name
        yield section, p


def upsert_course(session: Session, course_dir: Path) -> Course:
    course_path = str(course_dir.resolve())
    title = course_dir.name

    existing = session.exec(select(Course).where(Course.path == course_path)).first()
    if existing:
        if existing.title != title:
            existing.title = title
        return existing

    course = Course(path=course_path, title=title)
    session.add(course)
    session.flush()  # assign id
    return course


def upsert_lesson(
    session: Session,
    course_id: int,
    section: str,
    video_path: Path,
    order_key: str,
) -> Lesson:
    path_str = str(video_path.resolve())
    title = video_path.stem

    existing = session.exec(select(Lesson).where(Lesson.path == path_str)).first()
    if existing:
        changed = False
        if existing.course_id != course_id:
            existing.course_id = course_id
            changed = True
        if existing.section != section:
            existing.section = section
            changed = True
        if existing.title != title:
            existing.title = title
            changed = True
        if existing.order_key != order_key:
            existing.order_key = order_key
            changed = True
        if changed:
            session.add(existing)
        return existing

    lesson = Lesson(
        course_id=course_id,
        path=path_str,
        section=section,
        title=title,
        order_key=order_key,
    )
    session.add(lesson)
    return lesson


def scan_library(session: Session, courses_dir: Path) -> ScanStats:
    stats = ScanStats()

    if not courses_dir.exists() or not courses_dir.is_dir():
        return stats

    course_dirs = [p for p in courses_dir.iterdir() if p.is_dir()]
    course_dirs.sort(key=lambda p: natural_key(p.name))

    for course_dir in course_dirs:
        stats.courses_seen += 1
        course = upsert_course(session, course_dir)

        # Upsert lessons
        for section, video_path in iter_video_files(course_dir):
            stats.lessons_seen += 1
            # Order key: relative path within the course, good enough for stable ordering.
            rel = video_path.relative_to(course_dir)
            upsert_lesson(
                session=session,
                course_id=course.id,
                section=section,
                video_path=video_path,
                order_key=str(rel),
            )

    session.commit()
    return stats
