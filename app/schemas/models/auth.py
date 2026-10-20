from datetime import datetime
from typing import Optional

from sqlmodel import Field, SQLModel

from app.core.time import utcnow
from app.schemas.models.enums.status import TokenPurpose


class AuthToken(SQLModel, table=True):
    """One-time tokens for verifying an email address or resetting a password (stored hashed)."""

    __tablename__ = "auth_token"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    purpose: TokenPurpose
    token_hash: str = Field(unique=True, index=True, max_length=64)
    expires_at: datetime
    used_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=utcnow)


class RefreshSession(SQLModel, table=True):
    """A logged-in device. Revoking the row is what makes logout real."""

    __tablename__ = "refresh_session"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    token_hash: str = Field(unique=True, index=True, max_length=64)
    user_agent: Optional[str] = Field(default=None, max_length=255)
    created_at: datetime = Field(default_factory=utcnow)
    expires_at: datetime
    revoked_at: Optional[datetime] = None
