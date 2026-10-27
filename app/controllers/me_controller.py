from fastapi import APIRouter, status

from app.controllers.auth_controller import user_out
from app.dependencies import (
    AuthServiceDep,
    CurrentUser,
    InvitationServiceDep,
    OrganisationServiceDep,
    TaskServiceDep,
)
from app.schemas.requests.auth_requests import UpdateProfileRequest
from app.schemas.responses.responses import (
    InvitationOut,
    MyOrganisationOut,
    MyTodoOut,
    OrganisationOut,
    UserOut,
)

router = APIRouter(prefix="/api/me", tags=["me"])


def my_org_out(membership, organisation) -> MyOrganisationOut:
    return MyOrganisationOut(
        organisation=OrganisationOut(id=organisation.id, name=organisation.name, created_at=organisation.created_at),
        role=membership.role,
        joined_at=membership.joined_at,
    )


@router.get("", response_model=UserOut)
def me(user: CurrentUser):
    return user_out(user)


@router.patch("", response_model=UserOut)
def update_me(body: UpdateProfileRequest, user: CurrentUser, service: AuthServiceDep):
    return user_out(service.update_name(user, body.name))


@router.get("/organisations", response_model=list[MyOrganisationOut])
def my_organisations(user: CurrentUser, service: OrganisationServiceDep):
    return [my_org_out(m, o) for m, o in service.mine(user)]


@router.get("/invitations", response_model=list[InvitationOut])
def my_invitations(user: CurrentUser, service: InvitationServiceDep):
    return service.mine(user)


@router.post("/invitations/{invitation_id}/accept", response_model=MyOrganisationOut)
def accept_invitation(invitation_id: int, user: CurrentUser, service: InvitationServiceDep, orgs: OrganisationServiceDep):
    membership = service.accept(user, invitation_id)
    organisation = orgs.orgs.get(membership.organisation_id)
    return my_org_out(membership, organisation)


@router.post("/invitations/{invitation_id}/decline", status_code=status.HTTP_204_NO_CONTENT)
def decline_invitation(invitation_id: int, user: CurrentUser, service: InvitationServiceDep):
    service.decline(user, invitation_id)


@router.get("/todos", response_model=list[MyTodoOut])
def my_todos(user: CurrentUser, service: TaskServiceDep):
    return service.my_todos(user)
