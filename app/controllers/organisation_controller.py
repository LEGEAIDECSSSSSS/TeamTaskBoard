from fastapi import APIRouter, status

from app.controllers.me_controller import my_org_out
from app.dependencies import (
    CurrentUser,
    InvitationServiceDep,
    Membership,
    OrganisationServiceDep,
)
from app.schemas.requests.org_requests import (
    ChangeOrgRoleRequest,
    CreateOrganisationRequest,
    InviteRequest,
    UpdateOrganisationRequest,
)
from app.schemas.responses.responses import (
    AuditLogOut,
    InvitationOut,
    MyOrganisationOut,
    OrgMemberOut,
)

# Creating an organisation has no org id yet, so it lives on its own router.
create_router = APIRouter(prefix="/api/orgs", tags=["organisations"])
router = APIRouter(prefix="/api/orgs/{org_id}", tags=["organisations"])


@create_router.post("", response_model=MyOrganisationOut, status_code=status.HTTP_201_CREATED)
def create_organisation(body: CreateOrganisationRequest, user: CurrentUser, service: OrganisationServiceDep):
    organisation, membership = service.create(user, body.name)
    return my_org_out(membership, organisation)


@router.get("", response_model=MyOrganisationOut)
def get_organisation(membership: Membership, service: OrganisationServiceDep):
    return my_org_out(membership, service.orgs.get(membership.organisation_id))


@router.patch("", response_model=MyOrganisationOut)
def rename_organisation(body: UpdateOrganisationRequest, membership: Membership, service: OrganisationServiceDep):
    return my_org_out(membership, service.rename(membership, body.name))


@router.get("/members", response_model=list[OrgMemberOut])
def list_members(membership: Membership, service: OrganisationServiceDep):
    return service.members(membership)


@router.patch("/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def change_member_role(user_id: int, body: ChangeOrgRoleRequest, membership: Membership, service: OrganisationServiceDep):
    service.change_role(membership, user_id, body.role)


@router.delete("/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_member(user_id: int, membership: Membership, service: OrganisationServiceDep):
    service.remove_member(membership, user_id)


@router.post("/leave", status_code=status.HTTP_204_NO_CONTENT)
def leave_organisation(membership: Membership, service: OrganisationServiceDep):
    service.leave(membership)


@router.get("/invitations", response_model=list[InvitationOut])
def list_invitations(membership: Membership, service: InvitationServiceDep):
    return service.pending_for_org(membership)


@router.post("/invitations", response_model=InvitationOut, status_code=status.HTTP_201_CREATED)
def invite(body: InviteRequest, membership: Membership, service: InvitationServiceDep):
    return service.create(membership, body.email, body.role)


@router.delete("/invitations/{invitation_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_invitation(invitation_id: int, membership: Membership, service: InvitationServiceDep):
    service.revoke(membership, invitation_id)


@router.get("/activity", response_model=list[AuditLogOut])
def activity(membership: Membership, service: OrganisationServiceDep):
    return service.recent_activity(membership)
