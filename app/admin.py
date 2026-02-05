from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlmodel import Session, select

from .config import get_settings
from .models import Course
from .scan import scan_library
from .udemy_thumb import best_thumbnail_for_course_title


router = APIRouter()


@router.get("/admin", response_class=HTMLResponse)
def admin_home(request: Request, session: Session = Depends(lambda: None)):
    # NOTE: actual dependency injected in main when included (see include_router wrapper)
    return request


def build_admin_router(templates, meta_func, get_session_dep, set_scan_meta):
    r = APIRouter()

    @r.get("/admin", response_class=HTMLResponse)
    def admin_page(request: Request, session: Session = Depends(get_session_dep)):
        # Show lightweight feedback via query params.
        qp = dict(request.query_params)
        result = qp if qp else None
        return templates.TemplateResponse(request, "admin.html", {"result": result, **meta_func()})

    @r.post("/admin/scan")
    def admin_scan(session: Session = Depends(get_session_dep)):
        settings = get_settings()
        stats = scan_library(session, settings.courses_dir)
        set_scan_meta(stats)
        return RedirectResponse(
            url=f"/admin?scan=1&courses={stats.courses_seen}&lessons={stats.lessons_seen}",
            status_code=303,
        )

    @r.post("/admin/thumbnails")
    def admin_thumbs(session: Session = Depends(get_session_dep)):
        courses = session.exec(select(Course).order_by(Course.title)).all()
        updated = 0
        attempted = 0
        for c in courses:
            if c.thumbnail_url:
                continue
            attempted += 1
            thumb = best_thumbnail_for_course_title(c.title)
            if thumb:
                c.thumbnail_url = thumb
                session.add(c)
                updated += 1
        session.commit()
        return RedirectResponse(
            url=f"/admin?thumbs=1&attempted={attempted}&updated={updated}", status_code=303
        )

    return r
