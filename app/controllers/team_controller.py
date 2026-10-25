from fastapi import APIRouter, Response, status

from app.dependencies import Membership, TeamServiceDep
from app.schemas.requests.org_requests import (
    AddTeamMemberRequest,
    ChangeTeamRoleRequest,
    CreateTeamRequest,
    UpdateTeamRequest,
)
from app.schemas.responses.responses import TeamDetailOut, TeamOut

router = APIRouter(prefix="/api/orgs/{org_id}/teams", tags=["teams"])


@router.get("", response_model=list[TeamOut])
def list_teams(membership: Membership, service: TeamServiceDep):
    return service.list_teams(membership)


@router.post("", response_model=TeamDetailOut, status_code=status.HTTP_201_CREATED)
def create_team(body: CreateTeamRequest, membership: Membership, service: TeamServiceDep):
    return service.create(membership, body)


@router.get("/{team_id}", response_model=TeamDetailOut)
def get_team(team_id: int, membership: Membership, service: TeamServiceDep):
    return service.detail(membership, team_id)


@router.patch("/{team_id}", response_model=TeamDetailOut)
def update_team(team_id: int, body: UpdateTeamRequest, membership: Membership, service: TeamServiceDep):
    return service.update(membership, team_id, body)


@router.delete("/{team_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_team(team_id: int, membership: Membership, service: TeamServiceDep):
    service.delete(membership, team_id)


@router.post("/{team_id}/members", response_model=TeamDetailOut, status_code=status.HTTP_201_CREATED)
def add_team_member(team_id: int, body: AddTeamMemberRequest, membership: Membership, service: TeamServiceDep):
    return service.add_member(membership, team_id, body.user_id, body.role)


@router.patch("/{team_id}/members/{user_id}", response_model=TeamDetailOut)
def change_team_role(
    team_id: int, user_id: int, body: ChangeTeamRoleRequest, membership: Membership, service: TeamServiceDep
):
    return service.change_member_role(membership, team_id, user_id, body.role)


@router.delete("/{team_id}/members/{user_id}")
def remove_team_member(team_id: int, user_id: int, membership: Membership, service: TeamServiceDep):
    result = service.remove_member(membership, team_id, user_id)
    if result is None:
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    return result
