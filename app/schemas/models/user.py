from datetime import datetime
from typing import Optional

from sqlmodel import Field, SQLModel

from app.core.time import utcnow


class User(SQLModel, table=True):
    """A person. Holds identity only. Roles live on organisation and team memberships."""

    __tablename__ = "users"

    id: Optional[int] = Field(default=None, primary_key=True)
    email: str = Field(unique=True, index=True, max_length=254)
    name: str = Field(max_length=100)
    password_hash: str = Field(max_length=255)
    email_verified: bool = Field(default=False)
    email_verified_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=utcnow)
    last_login_at: Optional[datetime] = None
