from datetime import datetime

from sqlmodel import col, select

from app.core.time import utcnow
from app.repositories.base import BaseRepository
from app.schemas.models.auth import AuthToken, RefreshSession
from app.schemas.models.enums.status import TokenPurpose
from app.schemas.models.user import User


class UserRepository(BaseRepository):
    def get(self, user_id: int) -> User | None:
        return self.session.get(User, user_id)

    def find_by_email(self, email: str) -> User | None:
        return self.session.exec(select(User).where(User.email == email.lower())).first()


class AuthTokenRepository(BaseRepository):
    def create(self, user_id: int, purpose: TokenPurpose, token_hash: str, expires_at: datetime) -> AuthToken:
        return self.add(AuthToken(user_id=user_id, purpose=purpose, token_hash=token_hash, expires_at=expires_at))

    def find_valid(self, token_hash: str, purpose: TokenPurpose) -> AuthToken | None:
        token = self.session.exec(
            select(AuthToken).where(AuthToken.token_hash == token_hash, AuthToken.purpose == purpose)
        ).first()
        if token is None or token.used_at is not None or token.expires_at < utcnow():
            return None
        return token

    def invalidate_for_user(self, user_id: int, purpose: TokenPurpose) -> None:
        for token in self.session.exec(
            select(AuthToken).where(
                AuthToken.user_id == user_id, AuthToken.purpose == purpose, col(AuthToken.used_at).is_(None)
            )
        ).all():
            token.used_at = utcnow()
            self.session.add(token)
        self.session.flush()


class SessionRepository(BaseRepository):
    def create(self, user_id: int, token_hash: str, expires_at: datetime, user_agent: str | None) -> RefreshSession:
        return self.add(
            RefreshSession(user_id=user_id, token_hash=token_hash, expires_at=expires_at, user_agent=user_agent)
        )

    def find_by_hash(self, token_hash: str) -> RefreshSession | None:
        return self.session.exec(select(RefreshSession).where(RefreshSession.token_hash == token_hash)).first()

    def revoke(self, refresh_session: RefreshSession) -> None:
        if refresh_session.revoked_at is None:
            refresh_session.revoked_at = utcnow()
            self.session.add(refresh_session)
            self.session.flush()

    def revoke_all_for_user(self, user_id: int, except_hash: str | None = None) -> None:
        for refresh_session in self.session.exec(
            select(RefreshSession).where(RefreshSession.user_id == user_id, col(RefreshSession.revoked_at).is_(None))
        ).all():
            if except_hash and refresh_session.token_hash == except_hash:
                continue
            refresh_session.revoked_at = utcnow()
            self.session.add(refresh_session)
        self.session.flush()
