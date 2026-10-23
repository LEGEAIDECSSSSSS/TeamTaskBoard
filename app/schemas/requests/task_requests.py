from pydantic import BaseModel, Field

from app.schemas.models.enums.priority import Priority
from app.schemas.models.enums.status import Status
from app.schemas.types import ShortTitle, UTCDatetimeIn


class CreateTaskRequest(BaseModel):
    title: ShortTitle
    description: str | None = Field(default=None, max_length=5000)
    due_date: UTCDatetimeIn | None = None


class UpdateTaskRequest(BaseModel):
    title: ShortTitle | None = None
    description: str | None = Field(default=None, max_length=5000)
    due_date: UTCDatetimeIn | None = None
    clear_due_date: bool = False


class CreateTodoRequest(BaseModel):
    title: ShortTitle
    description: str | None = Field(default=None, max_length=5000)
    assigned_to_id: int | None = None
    priority: Priority = Priority.MEDIUM
    due: UTCDatetimeIn | None = None


class UpdateTodoRequest(BaseModel):
    title: ShortTitle | None = None
    description: str | None = Field(default=None, max_length=5000)
    assigned_to_id: int | None = None
    unassign: bool = False
    priority: Priority | None = None
    due: UTCDatetimeIn | None = None
    clear_due: bool = False


class ChangeStatusRequest(BaseModel):
    status: Status
