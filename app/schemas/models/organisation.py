from datetime import datetime
from typing import Optional

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel

from app.core.time import utcnow
from app.schemas.models.enums.role import OrgRole
from app.schemas.models.enums.status import InvitationStatus, MembershipStatus


class Organisation(SQLModel, table=True):
    __tablename__ = "organisation"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(max_length=100)
    created_by_id: int = Field(foreign_key="users.id")
    created_at: datetime = Field(default_factory=utcnow)


class OrganisationMember(SQLModel, table=True):
    """A person's membership of an organisation. Leaving keeps the row (status=left) so history survives
    and rejoining later reuses it."""

    __tablename__ = "organisation_member"
    __table_args__ = (UniqueConstraint("organisation_id", "user_id", name="uq_org_member"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    organisation_id: int = Field(foreign_key="organisation.id", index=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    role: OrgRole = Field(default=OrgRole.MEMBER)
    status: MembershipStatus = Field(default=MembershipStatus.ACTIVE)
    joined_at: datetime = Field(default_factory=utcnow)
    left_at: Optional[datetime] = None


class Invitation(SQLModel, table=True):
    """An invitation is the only way into an existing organisation. It carries the role being granted."""

    __tablename__ = "invitation"

    id: Optional[int] = Field(default=None, primary_key=True)
    organisation_id: int = Field(foreign_key="organisation.id", index=True)
    email: str = Field(index=True, max_length=254)
    role: OrgRole = Field(default=OrgRole.MEMBER)
    status: InvitationStatus = Field(default=InvitationStatus.PENDING)
    invited_by_id: int = Field(foreign_key="users.id")
    created_at: datetime = Field(default_factory=utcnow)
    expires_at: datetime
    responded_at: Optional[datetime] = None


class AuditLog(SQLModel, table=True):
    __tablename__ = "audit_log"

    id: Optional[int] = Field(default=None, primary_key=True)
    organisation_id: int = Field(foreign_key="organisation.id", index=True)
    actor_id: Optional[int] = Field(default=None, foreign_key="users.id")
    action: str = Field(max_length=60)
    target_type: Optional[str] = Field(default=None, max_length=40)
    target_id: Optional[int] = None
    detail: Optional[str] = Field(default=None, max_length=500)
    created_at: datetime = Field(default_factory=utcnow, index=True)
