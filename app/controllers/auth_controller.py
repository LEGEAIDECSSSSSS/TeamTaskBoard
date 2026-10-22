from fastapi import APIRouter, Request, Response, status

from app.config.settings import settings
from app.core.rate_limit import email_limiter, login_limiter, register_limiter
from app.dependencies import ACCESS_COOKIE, REFRESH_COOKIE, AuthServiceDep, CurrentUser
from app.schemas.requests.auth_requests import (
    ChangePasswordRequest,
    EmailRequest,
    LoginRequest,
    RegisterRequest,
    ResetPasswordRequest,
    TokenRequest,
)
from app.schemas.responses.responses import UserOut

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def set_auth_cookies(response: Response, access: str, refresh: str) -> None:
    common = {"httponly": True, "secure": settings.is_production, "samesite": "lax"}
    response.set_cookie(ACCESS_COOKIE, access, max_age=settings.ACCESS_TOKEN_MINUTES * 60, path="/api", **common)
    response.set_cookie(
        REFRESH_COOKIE, refresh, max_age=settings.REFRESH_TOKEN_DAYS * 86400, path="/api/auth", **common
    )


def clear_auth_cookies(response: Response) -> None:
    response.delete_cookie(ACCESS_COOKIE, path="/api")
    response.delete_cookie(REFRESH_COOKIE, path="/api/auth")


def user_out(user) -> UserOut:
    return UserOut(
        id=user.id,
        email=user.email,
        name=user.name,
        email_verified=user.email_verified,
        created_at=user.created_at,
    )


@router.post("/register", status_code=status.HTTP_201_CREATED)
def register(body: RegisterRequest, request: Request, service: AuthServiceDep):
    register_limiter.hit(_client_ip(request))
    user = service.register(body)
    return {"email": user.email, "message": "Check your inbox to confirm your email address."}


@router.post("/verify-email", response_model=UserOut)
def verify_email(body: TokenRequest, service: AuthServiceDep):
    return user_out(service.verify_email(body.token))


@router.post("/resend-verification", status_code=status.HTTP_202_ACCEPTED)
def resend_verification(body: EmailRequest, service: AuthServiceDep):
    email_limiter.hit(f"verify:{body.email}")
    service.resend_verification(body.email)
    return {"message": "If that account needs confirming, we've sent a new link."}


@router.post("/login", response_model=UserOut)
def login(body: LoginRequest, request: Request, response: Response, service: AuthServiceDep):
    key = f"{_client_ip(request)}:{body.email}"
    login_limiter.hit(key)
    user, access, refresh = service.login(body, request.headers.get("user-agent"))
    login_limiter.reset(key)
    set_auth_cookies(response, access, refresh)
    return user_out(user)


@router.post("/refresh", response_model=UserOut)
def refresh(request: Request, response: Response, service: AuthServiceDep):
    user, access, new_refresh = service.refresh(
        request.cookies.get(REFRESH_COOKIE), request.headers.get("user-agent")
    )
    set_auth_cookies(response, access, new_refresh)
    return user_out(user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(request: Request, response: Response, service: AuthServiceDep):
    service.logout(request.cookies.get(REFRESH_COOKIE))
    clear_auth_cookies(response)


@router.post("/forgot-password", status_code=status.HTTP_202_ACCEPTED)
def forgot_password(body: EmailRequest, service: AuthServiceDep):
    email_limiter.hit(f"reset:{body.email}")
    service.forgot_password(body.email)
    return {"message": "If an account exists for that email, a reset link is on its way."}


@router.post("/reset-password", status_code=status.HTTP_204_NO_CONTENT)
def reset_password(body: ResetPasswordRequest, service: AuthServiceDep):
    service.reset_password(body)


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(body: ChangePasswordRequest, request: Request, user: CurrentUser, service: AuthServiceDep):
    # Lives under /api/auth so the browser sends the refresh cookie, which tells us which session to keep.
    service.change_password(user, body, request.cookies.get(REFRESH_COOKIE))
