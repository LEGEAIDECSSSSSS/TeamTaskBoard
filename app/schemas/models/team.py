from datetime import datetime
from typing import Optional

from sqlalchemy import Text, UniqueConstraint
from sqlmodel import Field, SQLModel

from app.core.time import utcnow
from app.schemas.models.enums.role import TeamRole


class Team(SQLModel, table=True):
    __tablename__ = "team"
    __table_args__ = (UniqueConstraint("organisation_id", "name", name="uq_team_name_per_org"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    organisation_id: int = Field(foreign_key="organisation.id", index=True)
    name: str = Field(min_length=2, max_length=80)
    description: Optional[str] = Field(default=None, sa_type=Text)
    created_by_id: int = Field(foreign_key="users.id")
    created_at: datetime = Field(default_factory=utcnow)


class TeamMember(SQLModel, table=True):
    """A person's role in one team. left_at is None while they are on the team."""

    __tablename__ = "team_member"
    __table_args__ = (UniqueConstraint("team_id", "user_id", name="uq_team_member"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    team_id: int = Field(foreign_key="team.id", index=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    role: TeamRole = Field(default=TeamRole.MEMBER)
    joined_at: datetime = Field(default_factory=utcnow)
    left_at: Optional[datetime] = None
