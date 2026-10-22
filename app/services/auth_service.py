from datetime import timedelta

from sqlmodel import Session

from app.config.settings import settings
from app.core.security import (
    create_access_token,
    generate_token,
    hash_password,
    hash_token,
    verify_password,
)
from app.core.time import utcnow
from app.exceptions.exception import BadRequestError, ConflictError, ForbiddenError, UnauthorizedError
from app.repositories.user_repository import AuthTokenRepository, SessionRepository, UserRepository
from app.schemas.models.enums.status import TokenPurpose
from app.schemas.models.user import User
from app.schemas.requests.auth_requests import (
    ChangePasswordRequest,
    LoginRequest,
    RegisterRequest,
    ResetPasswordRequest,
)
from app.services.email_service import Mailer


class AuthService:
    def __init__(self, session: Session, mailer: Mailer):
        self.session = session
        self.mailer = mailer
        self.users = UserRepository(session)
        self.tokens = AuthTokenRepository(session)
        self.sessions = SessionRepository(session)

    # -- registration & email verification --------------------------------
    def register(self, request: RegisterRequest) -> User:
        if self.users.find_by_email(request.email) is not None:
            raise ConflictError("An account with this email already exists. Try logging in instead.", "email_taken")
        user = self.users.add(
            User(name=request.name, email=request.email, password_hash=hash_password(request.password))
        )
        self._send_verification(user)
        self.session.commit()
        return user

    def resend_verification(self, email: str) -> None:
        """Always succeeds from the caller's point of view, so it can't be used to discover accounts."""
        user = self.users.find_by_email(email)
        if user is None or user.email_verified:
            return
        self._send_verification(user)
        self.session.commit()

    def verify_email(self, token: str) -> User:
        record = self.tokens.find_valid(hash_token(token), TokenPurpose.VERIFY_EMAIL)
        if record is None:
            raise BadRequestError(
                "This verification link is invalid or has expired. Request a new one from the login page.",
                "invalid_token",
            )
        user = self.users.get(record.user_id)
        if user is None:
            raise BadRequestError("This verification link is invalid or has expired.", "invalid_token")
        user.email_verified = True
        user.email_verified_at = utcnow()
        record.used_at = utcnow()
        self.session.add(user)
        self.session.add(record)
        self.session.commit()
        return user

    def _send_verification(self, user: User) -> None:
        self.tokens.invalidate_for_user(user.id, TokenPurpose.VERIFY_EMAIL)
        token = generate_token()
        self.tokens.create(
            user.id,
            TokenPurpose.VERIFY_EMAIL,
            hash_token(token),
            utcnow() + timedelta(hours=settings.EMAIL_VERIFICATION_HOURS),
        )
        self.mailer.send_verification(user.name, user.email, token)

    # -- login / sessions ---------------------------------------------------
    def login(self, request: LoginRequest, user_agent: str | None) -> tuple[User, str, str]:
        user = self.users.find_by_email(request.email)
        if not verify_password(request.password, user.password_hash if user else None) or user is None:
            raise UnauthorizedError("Incorrect email or password.", "invalid_credentials")
        if not user.email_verified:
            raise ForbiddenError("Confirm your email address before logging in.", "email_not_verified")
        user.last_login_at = utcnow()
        self.session.add(user)
        refresh = self._start_session(user, user_agent)
        self.session.commit()
        return user, create_access_token(user.id), refresh

    def refresh(self, refresh_token: str | None, user_agent: str | None) -> tuple[User, str, str]:
        if not refresh_token:
            raise UnauthorizedError("Session expired. Log in again.", "session_expired")
        current = self.sessions.find_by_hash(hash_token(refresh_token))
        if current is None:
            raise UnauthorizedError("Session expired. Log in again.", "session_expired")
        if current.revoked_at is not None:
            # An old token was replayed: assume it leaked and sign the account out everywhere.
            self.sessions.revoke_all_for_user(current.user_id)
            self.session.commit()
            raise UnauthorizedError("Session expired. Log in again.", "session_expired")
        user = self.users.get(current.user_id)
        if current.expires_at < utcnow() or user is None:
            raise UnauthorizedError("Session expired. Log in again.", "session_expired")
        self.sessions.revoke(current)
        new_refresh = self._start_session(user, user_agent)
        self.session.commit()
        return user, create_access_token(user.id), new_refresh

    def logout(self, refresh_token: str | None) -> None:
        if not refresh_token:
            return
        current = self.sessions.find_by_hash(hash_token(refresh_token))
        if current is not None:
            self.sessions.revoke(current)
            self.session.commit()

    def _start_session(self, user: User, user_agent: str | None) -> str:
        token = generate_token()
        self.sessions.create(
            user.id,
            hash_token(token),
            utcnow() + timedelta(days=settings.REFRESH_TOKEN_DAYS),
            (user_agent or "")[:255] or None,
        )
        return token

    # -- passwords ----------------------------------------------------------
    def forgot_password(self, email: str) -> None:
        user = self.users.find_by_email(email)
        if user is None:
            return
        self.tokens.invalidate_for_user(user.id, TokenPurpose.RESET_PASSWORD)
        token = generate_token()
        self.tokens.create(
            user.id,
            TokenPurpose.RESET_PASSWORD,
            hash_token(token),
            utcnow() + timedelta(minutes=settings.PASSWORD_RESET_MINUTES),
        )
        self.mailer.send_password_reset(user.name, user.email, token)
        self.session.commit()

    def reset_password(self, request: ResetPasswordRequest) -> None:
        record = self.tokens.find_valid(hash_token(request.token), TokenPurpose.RESET_PASSWORD)
        user = self.users.get(record.user_id) if record else None
        if record is None or user is None:
            raise BadRequestError(
                "This reset link is invalid or has expired. Request a new one.", "invalid_token"
            )
        user.password_hash = hash_password(request.password)
        if not user.email_verified:  # receiving the reset email proves the address is theirs
            user.email_verified = True
            user.email_verified_at = utcnow()
        record.used_at = utcnow()
        self.session.add(user)
        self.session.add(record)
        self.sessions.revoke_all_for_user(user.id)
        self.session.commit()

    def change_password(self, user: User, request: ChangePasswordRequest, current_refresh_token: str | None) -> None:
        if not verify_password(request.current_password, user.password_hash):
            raise BadRequestError("Your current password is incorrect.", "wrong_password")
        user.password_hash = hash_password(request.new_password)
        self.session.add(user)
        keep = hash_token(current_refresh_token) if current_refresh_token else None
        self.sessions.revoke_all_for_user(user.id, except_hash=keep)
        self.session.commit()

    def update_name(self, user: User, name: str) -> User:
        user.name = name
        self.session.add(user)
        self.session.commit()
        return user
