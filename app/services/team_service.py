from sqlmodel import Session

from app.core.time import utcnow
from app.exceptions.exception import BadRequestError, ConflictError, ForbiddenError, NotFoundError
from app.repositories.organisation_repository import AuditRepository, OrganisationRepository
from app.repositories.task_repository import TaskRepository, TodoRepository
from app.repositories.team_repository import TeamRepository
from app.repositories.user_repository import UserRepository
from app.schemas.models.enums.role import TeamRole
from app.schemas.models.organisation import OrganisationMember
from app.schemas.models.team import Team, TeamMember
from app.schemas.requests.org_requests import CreateTeamRequest, UpdateTeamRequest
from app.schemas.responses.responses import LeadOut, TeamDetailOut, TeamMemberOut, TeamOut
from app.services.access import AccessControl


class TeamService:
    def __init__(self, session: Session):
        self.session = session
        self.teams = TeamRepository(session)
        self.tasks = TaskRepository(session)
        self.todos = TodoRepository(session)
        self.orgs = OrganisationRepository(session)
        self.users = UserRepository(session)
        self.audit = AuditRepository(session)
        self.access = AccessControl(session)

    # -- reading --------------------------------------------------------------
    def list_teams(self, actor: OrganisationMember) -> list[TeamOut]:
        if self.access.is_org_admin(actor):
            teams = self.teams.list_for_org(actor.organisation_id)
        else:
            teams = self.teams.list_for_user(actor.organisation_id, actor.user_id)
        return self._to_out(teams, actor.user_id)

    def detail(self, actor: OrganisationMember, team_id: int) -> TeamDetailOut:
        team = self.access.team_for(actor, team_id)
        self.access.require_view(actor, team)
        base = self._to_out([team], actor.user_id)[0]
        members = [
            TeamMemberOut(user_id=u.id, name=u.name, email=u.email, role=tm.role, joined_at=tm.joined_at)
            for tm, u in self.teams.active_members(team.id)
        ]
        return TeamDetailOut(**base.model_dump(), members=members, can_manage=self.access.can_manage_team(actor, team))

    # -- writing --------------------------------------------------------------
    def create(self, actor: OrganisationMember, request: CreateTeamRequest) -> TeamDetailOut:
        if not self.access.is_org_admin(actor):
            raise ForbiddenError("Only owners and admins can create teams.")
        name = request.name.strip()
        if self.teams.find_by_name(actor.organisation_id, name):
            raise ConflictError("A team with this name already exists in your organisation.", "team_name_taken")
        if not self.orgs.active_membership(actor.organisation_id, request.lead_user_id):
            raise BadRequestError("The team lead must be a member of this organisation.")
        team = self.teams.add(
            Team(
                organisation_id=actor.organisation_id,
                name=name,
                description=(request.description or "").strip() or None,
                created_by_id=actor.user_id,
            )
        )
        self.teams.add(TeamMember(team_id=team.id, user_id=request.lead_user_id, role=TeamRole.LEAD))
        self.audit.log(actor.organisation_id, actor.user_id, "team.created", "team", team.id, name)
        self.session.commit()
        return self.detail(actor, team.id)

    def update(self, actor: OrganisationMember, team_id: int, request: UpdateTeamRequest) -> TeamDetailOut:
        team = self.access.team_for(actor, team_id)
        self.access.require_manage(actor, team)
        if request.name is not None:
            name = request.name.strip()
            clash = self.teams.find_by_name(actor.organisation_id, name)
            if clash and clash.id != team.id:
                raise ConflictError("A team with this name already exists in your organisation.", "team_name_taken")
            team.name = name
        if request.description is not None:
            team.description = request.description.strip() or None
        self.session.add(team)
        self.session.commit()
        return self.detail(actor, team.id)

    def delete(self, actor: OrganisationMember, team_id: int) -> None:
        team = self.access.team_for(actor, team_id)
        if not self.access.is_org_admin(actor):
            raise ForbiddenError("Only owners and admins can delete teams.")
        name = team.name
        for task in self.tasks.list_for_team(team.id):
            self.todos.delete_for_task(task.id)
            self.tasks.delete(task)
        self.teams.delete_members(team.id)
        self.teams.delete(team)
        self.audit.log(actor.organisation_id, actor.user_id, "team.deleted", "team", team_id, name)
        self.session.commit()

    # -- team membership --------------------------------------------------------
    def add_member(self, actor: OrganisationMember, team_id: int, user_id: int, role: TeamRole) -> TeamDetailOut:
        team = self.access.team_for(actor, team_id)
        self.access.require_manage(actor, team)
        if not self.orgs.active_membership(actor.organisation_id, user_id):
            raise BadRequestError("Only people in this organisation can join its teams. Invite them to the organisation first.")
        row = self.teams.membership(team.id, user_id)
        if row and row.left_at is None:
            raise ConflictError("That person is already on this team.", "already_on_team")
        if row:
            row.left_at = None
            row.role = role
            row.joined_at = utcnow()
            self.session.add(row)
        else:
            self.teams.add(TeamMember(team_id=team.id, user_id=user_id, role=role))
        self.audit.log(
            actor.organisation_id, actor.user_id, "team.member_added", "team", team.id, f"{self._label(user_id)} → {team.name}"
        )
        self.session.commit()
        return self.detail(actor, team.id)

    def change_member_role(
        self, actor: OrganisationMember, team_id: int, user_id: int, role: TeamRole
    ) -> TeamDetailOut:
        team = self.access.team_for(actor, team_id)
        self.access.require_manage(actor, team)
        row = self._active_row(team.id, user_id)
        if row.role == role:
            return self.detail(actor, team.id)
        self._guard_last_lead(actor, team, row, "demote")
        row.role = role
        self.session.add(row)
        self.audit.log(
            actor.organisation_id,
            actor.user_id,
            "team.role_changed",
            "team",
            team.id,
            f"{self._label(user_id)} is now {role.value} of {team.name}",
        )
        self.session.commit()
        return self.detail(actor, team.id)

    def remove_member(self, actor: OrganisationMember, team_id: int, user_id: int) -> TeamDetailOut | None:
        team = self.access.team_for(actor, team_id)
        self.access.require_manage(actor, team)
        row = self._active_row(team.id, user_id)
        self._guard_last_lead(actor, team, row, "remove")
        row.left_at = utcnow()
        self.session.add(row)
        released = self.todos.todos_in_team_for_user(team.id, user_id)
        for todo in released:
            todo.assigned_to_id = None
            todo.updated_at = utcnow()
            self.session.add(todo)
        self.audit.log(
            actor.organisation_id,
            actor.user_id,
            "team.member_removed",
            "team",
            team.id,
            f"{self._label(user_id)} ← {team.name} · {len(released)} open todo(s) unassigned",
        )
        self.session.commit()
        if user_id == actor.user_id and not self.access.is_org_admin(actor):
            return None  # they removed themselves and can no longer see the team
        return self.detail(actor, team.id)

    # -- helpers ------------------------------------------------------------------
    def _active_row(self, team_id: int, user_id: int) -> TeamMember:
        row = self.teams.membership(team_id, user_id)
        if row is None or row.left_at is not None:
            raise NotFoundError("That person is not on this team.")
        return row

    def _guard_last_lead(self, actor: OrganisationMember, team: Team, row: TeamMember, verb: str) -> None:
        """A lead can't leave their own team without a lead. An organisation admin can, and can appoint another later."""
        if row.role == TeamRole.LEAD and self.teams.lead_count(team.id) <= 1 and not self.access.is_org_admin(actor):
            raise ConflictError(f"You can't {verb} the only team lead. Make someone else a lead first.", "last_lead")

    def _label(self, user_id: int) -> str:
        user = self.users.get(user_id)
        return user.name if user else f"user {user_id}"

    def _to_out(self, teams: list[Team], user_id: int) -> list[TeamOut]:
        ids = [t.id for t in teams]
        member_counts = self.teams.member_counts(ids)
        leads = self.teams.leads(ids)
        todo_counts = self.teams.todo_counts(ids)
        my_roles = self.teams.my_roles(ids, user_id)
        return [
            TeamOut(
                id=t.id,
                organisation_id=t.organisation_id,
                name=t.name,
                description=t.description,
                created_at=t.created_at,
                member_count=member_counts.get(t.id, 0),
                open_todo_count=todo_counts.get(t.id, (0, 0))[0],
                overdue_todo_count=todo_counts.get(t.id, (0, 0))[1],
                leads=[LeadOut(user_id=uid, name=name) for uid, name in leads.get(t.id, [])],
                my_role=my_roles.get(t.id),
            )
            for t in teams
        ]
