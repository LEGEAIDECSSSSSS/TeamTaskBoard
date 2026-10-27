from typing import Annotated

from fastapi import BackgroundTasks, Depends, Request
from sqlmodel import Session

from app.config.settings import engine
from app.core.security import decode_access_token
from app.exceptions.exception import NotFoundError, UnauthorizedError
from app.repositories.organisation_repository import OrganisationRepository
from app.schemas.models.organisation import OrganisationMember
from app.schemas.models.user import User
from app.services.auth_service import AuthService
from app.services.email_service import Mailer
from app.services.organisation_service import InvitationService, OrganisationService
from app.services.task_service import TaskService
from app.services.team_service import TeamService

ACCESS_COOKIE = "access_token"
REFRESH_COOKIE = "refresh_token"


def get_session():
    with Session(engine) as session:
        yield session


SessionDep = Annotated[Session, Depends(get_session)]


def get_mailer(background_tasks: BackgroundTasks) -> Mailer:
    return Mailer(background_tasks)


MailerDep = Annotated[Mailer, Depends(get_mailer)]


# -- who is calling ------------------------------------------------------------------
def get_current_user(request: Request, session: SessionDep) -> User:
    token = request.cookies.get(ACCESS_COOKIE)
    if not token:
        header = request.headers.get("authorization", "")
        if header.lower().startswith("bearer "):
            token = header[7:].strip()
    user_id = decode_access_token(token) if token else None
    user = session.get(User, user_id) if user_id else None
    if user is None:
        raise UnauthorizedError("Please log in to continue.", "not_authenticated")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def get_membership(org_id: int, user: CurrentUser, session: SessionDep) -> OrganisationMember:
    """The caller's active membership of the organisation in the URL.

    Every organisation-scoped route depends on this, so a person can only ever act inside an organisation
    they currently belong to, with the role they hold *there*.
    """
    membership = OrganisationRepository(session).active_membership(org_id, user.id)
    if membership is None:
        raise NotFoundError("Organisation not found.")
    return membership


Membership = Annotated[OrganisationMember, Depends(get_membership)]


# -- services ----------------------------------------------------------------------------
def get_auth_service(session: SessionDep, mailer: MailerDep) -> AuthService:
    return AuthService(session, mailer)


def get_organisation_service(session: SessionDep) -> OrganisationService:
    return OrganisationService(session)


def get_invitation_service(session: SessionDep, mailer: MailerDep) -> InvitationService:
    return InvitationService(session, mailer)


def get_team_service(session: SessionDep) -> TeamService:
    return TeamService(session)


def get_task_service(session: SessionDep) -> TaskService:
    return TaskService(session)


AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]
OrganisationServiceDep = Annotated[OrganisationService, Depends(get_organisation_service)]
InvitationServiceDep = Annotated[InvitationService, Depends(get_invitation_service)]
TeamServiceDep = Annotated[TeamService, Depends(get_team_service)]
TaskServiceDep = Annotated[TaskService, Depends(get_task_service)]
