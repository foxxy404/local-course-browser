from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlmodel import SQLModel, Field, UniqueConstraint


class Course(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)

    # Absolute path to course directory (unique)
    path: str = Field(index=True, nullable=False)
    title: str = Field(index=True, nullable=False)

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    __table_args__ = (UniqueConstraint("path"),)


class Lesson(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)

    course_id: int = Field(index=True, nullable=False)

    # Absolute path to the video file (unique)
    path: str = Field(index=True, nullable=False)

    section: str = Field(index=True, nullable=False)
    title: str = Field(index=True, nullable=False)

    # Sort key within course
    order_key: str = Field(index=True, nullable=False)

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    __table_args__ = (UniqueConstraint("path"),)


class Progress(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)

    lesson_id: int = Field(index=True, nullable=False)

    # Single-user MVP: last playback position
    position_seconds: float = Field(default=0.0, nullable=False)
    completed: bool = Field(default=False, nullable=False)

    updated_at: datetime = Field(default_factory=datetime.utcnow)

    __table_args__ = (UniqueConstraint("lesson_id"),)
