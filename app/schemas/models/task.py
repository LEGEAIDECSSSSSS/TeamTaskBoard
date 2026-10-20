from datetime import datetime
from typing import Optional

from sqlalchemy import Text, UniqueConstraint
from sqlmodel import Field, SQLModel

from app.core.time import utcnow


class Task(SQLModel, table=True):
    """A body of work for a team. It is broken down into todos."""

    __tablename__ = "task"
    __table_args__ = (UniqueConstraint("team_id", "title", name="uq_task_title_per_team"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    team_id: int = Field(foreign_key="team.id", index=True)
    title: str = Field(max_length=150)
    description: Optional[str] = Field(default=None, sa_type=Text)
    due_date: Optional[datetime] = None
    created_by_id: int = Field(foreign_key="users.id")
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
