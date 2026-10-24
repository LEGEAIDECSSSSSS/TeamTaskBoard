from pydantic import BaseModel, Field

from app.schemas.models.enums.role import OrgRole, TeamRole
from app.schemas.types import NormalizedEmail, OrgName


class CreateOrganisationRequest(BaseModel):
    name: OrgName


class UpdateOrganisationRequest(BaseModel):
    name: OrgName


class ChangeOrgRoleRequest(BaseModel):
    role: OrgRole


class InviteRequest(BaseModel):
    email: NormalizedEmail
    role: OrgRole = OrgRole.MEMBER


class CreateTeamRequest(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    description: str | None = Field(default=None, max_length=2000)
    lead_user_id: int


class UpdateTeamRequest(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=80)
    description: str | None = Field(default=None, max_length=2000)


class AddTeamMemberRequest(BaseModel):
    user_id: int
    role: TeamRole = TeamRole.MEMBER


class ChangeTeamRoleRequest(BaseModel):
    role: TeamRole
