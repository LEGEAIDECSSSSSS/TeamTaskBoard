from sqlmodel import Session

from app.exceptions.exception import ForbiddenError, NotFoundError
from app.repositories.team_repository import TeamRepository
from app.schemas.models.enums.role import OrgRole, TeamRole
from app.schemas.models.organisation import OrganisationMember
from app.schemas.models.team import Team


class AccessControl:
    """Single place for the "who may do what" rules.

    Organisation role (owner/admin/member) and team role (lead/member) are independent: authority in one
    team or organisation never carries over to another.
    """

    def __init__(self, session: Session):
        self.teams = TeamRepository(session)

    @staticmethod
    def is_org_admin(membership: OrganisationMember) -> bool:
        return membership.role in (OrgRole.OWNER, OrgRole.ADMIN)

    def team_for(self, membership: OrganisationMember, team_id: int) -> Team:
        team = self.teams.get(team_id)
        # A team from another organisation looks exactly like a team that doesn't exist.
        if team is None or team.organisation_id != membership.organisation_id:
            raise NotFoundError("Team not found.")
        return team

    def team_role(self, user_id: int, team_id: int) -> TeamRole | None:
        return self.teams.active_role(team_id, user_id)

    def can_manage_team(self, membership: OrganisationMember, team: Team) -> bool:
        return self.is_org_admin(membership) or self.team_role(membership.user_id, team.id) == TeamRole.LEAD

    def require_view(self, membership: OrganisationMember, team: Team) -> None:
        if not (self.is_org_admin(membership) or self.team_role(membership.user_id, team.id) is not None):
            raise ForbiddenError("You are not on this team.")

    def require_manage(self, membership: OrganisationMember, team: Team) -> None:
        if not self.can_manage_team(membership, team):
            raise ForbiddenError("Only the team lead or an organisation admin can do this.")
