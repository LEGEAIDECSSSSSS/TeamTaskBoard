from datetime import datetime
from typing import Optional

from sqlalchemy import Text
from sqlmodel import Field, SQLModel

from app.core.time import utcnow
from app.schemas.models.enums.priority import Priority
from app.schemas.models.enums.status import Status


class Todo(SQLModel, table=True):
    """A card on the board. Overdue is derived from `due` and `progress`, not stored."""

    __tablename__ = "todo"

    id: Optional[int] = Field(default=None, primary_key=True)
    task_id: int = Field(foreign_key="task.id", index=True)
    title: str = Field(max_length=150)
    description: Optional[str] = Field(default=None, sa_type=Text)
    assigned_to_id: Optional[int] = Field(default=None, foreign_key="users.id", index=True)
    priority: Priority = Field(default=Priority.MEDIUM)
    progress: Status = Field(default=Status.TODO)
    due: Optional[datetime] = None
    created_by_id: int = Field(foreign_key="users.id")
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
    completed_at: Optional[datetime] = None
