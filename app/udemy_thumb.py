from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional
from urllib.parse import quote_plus

import httpx
from rapidfuzz import fuzz


@dataclass
class UdemyCandidate:
    title: str
    url: str
    image: Optional[str]
    score: float


_UDEMY_API = "https://www.udemy.com/api-2.0/courses/"


def _clean(s: str) -> str:
    s = s.strip()
    s = re.sub(r"\s+", " ", s)
    return s


def search_udemy_candidates(query: str, limit: int = 5, timeout_s: float = 10.0) -> list[UdemyCandidate]:
    """Best-effort Udemy search.

    Notes:
    - This uses an undocumented endpoint and may break or rate-limit.
    - It *does not* require auth (today), but Udemy can change that anytime.
    """

    q = _clean(query)
    if not q:
        return []

    params = {
        "search": q,
        "page": 1,
        "page_size": min(20, max(1, limit)),
        "fields[course]": "title,url,image_480x270,image_240x135,image_125_H",
    }

    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) Udemy-Local/0.1",
        "Accept": "application/json,text/plain,*/*",
        "Referer": "https://www.udemy.com/",
    }

    out: list[UdemyCandidate] = []
    with httpx.Client(follow_redirects=True, timeout=timeout_s, headers=headers) as client:
        r = client.get(_UDEMY_API, params=params)
        r.raise_for_status()
        data = r.json()

    results = data.get("results") or []
    for item in results:
        title = _clean(str(item.get("title") or ""))
        url = str(item.get("url") or "")
        if url and url.startswith("/"):
            url = "https://www.udemy.com" + url

        img = item.get("image_480x270") or item.get("image_240x135") or item.get("image_125_H")
        img = str(img) if img else None

        if not title:
            continue

        score = fuzz.token_set_ratio(q, title)
        out.append(UdemyCandidate(title=title, url=url, image=img, score=score))

    out.sort(key=lambda c: c.score, reverse=True)
    return out[:limit]


def best_thumbnail_for_course_title(title: str) -> Optional[str]:
    candidates = search_udemy_candidates(title, limit=5)
    if not candidates:
        return None

    best = candidates[0]
    # If the match is weak, don't attach something random.
    if best.score < 70:
        return None
    return best.image
