from pydantic import BaseModel

from app.schemas.models.enums.priority import Priority
from app.schemas.models.enums.role import OrgRole, TeamRole
from app.schemas.models.enums.status import InvitationStatus, Status
from app.schemas.types import UTCDatetime


class UserOut(BaseModel):
    id: int
    email: str
    name: str
    email_verified: bool
    created_at: UTCDatetime


class OrganisationOut(BaseModel):
    id: int
    name: str
    created_at: UTCDatetime


class MyOrganisationOut(BaseModel):
    organisation: OrganisationOut
    role: OrgRole
    joined_at: UTCDatetime


class OrgMemberOut(BaseModel):
    user_id: int
    name: str
    email: str
    role: OrgRole
    joined_at: UTCDatetime
    team_count: int = 0


class InvitationOut(BaseModel):
    id: int
    organisation_id: int
    organisation_name: str
    email: str
    role: OrgRole
    status: InvitationStatus
    invited_by_name: str
    created_at: UTCDatetime
    expires_at: UTCDatetime


class LeadOut(BaseModel):
    user_id: int
    name: str


class TeamOut(BaseModel):
    id: int
    organisation_id: int
    name: str
    description: str | None
    created_at: UTCDatetime
    member_count: int
    open_todo_count: int
    overdue_todo_count: int
    leads: list[LeadOut]
    my_role: TeamRole | None


class TeamMemberOut(BaseModel):
    user_id: int
    name: str
    email: str
    role: TeamRole
    joined_at: UTCDatetime


class TeamDetailOut(TeamOut):
    members: list[TeamMemberOut]
    can_manage: bool


class TaskOut(BaseModel):
    id: int
    team_id: int
    title: str
    description: str | None
    due_date: UTCDatetime | None
    created_at: UTCDatetime
    todo_count: int
    done_count: int


class TodoOut(BaseModel):
    id: int
    task_id: int
    task_title: str
    team_id: int
    title: str
    description: str | None
    assigned_to_id: int | None
    assigned_to_name: str | None
    priority: Priority
    progress: Status
    due: UTCDatetime | None
    is_late: bool
    created_at: UTCDatetime
    updated_at: UTCDatetime
    completed_at: UTCDatetime | None


class MyTodoOut(TodoOut):
    organisation_id: int
    organisation_name: str
    team_name: str


class AuditLogOut(BaseModel):
    id: int
    actor_name: str | None
    action: str
    target_type: str | None
    target_id: int | None
    detail: str | None
    created_at: UTCDatetime
