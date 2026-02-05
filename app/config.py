from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    courses_dir: Path
    database_url: str


def get_settings() -> Settings:
    courses_dir_raw = os.getenv("COURSES_DIR", "").strip()
    if not courses_dir_raw:
        # Intentionally loud: app can't function without this.
        courses_dir = Path("./courses").resolve()
    else:
        courses_dir = Path(courses_dir_raw).expanduser().resolve()

    database_url = os.getenv("DATABASE_URL", "sqlite:///./udemy_local.db").strip()

    return Settings(courses_dir=courses_dir, database_url=database_url)
