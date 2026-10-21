from sqlmodel import col, func, select

from app.core.time import utcnow
from app.repositories.base import BaseRepository
from app.schemas.models.enums.role import TeamRole
from app.schemas.models.enums.status import Status
from app.schemas.models.task import Task
from app.schemas.models.team import Team, TeamMember
from app.schemas.models.todo import Todo
from app.schemas.models.user import User


class TeamRepository(BaseRepository):
    def get(self, team_id: int) -> Team | None:
        return self.session.get(Team, team_id)

    def find_by_name(self, organisation_id: int, name: str) -> Team | None:
        return self.session.exec(
            select(Team).where(Team.organisation_id == organisation_id, func.lower(Team.name) == name.lower())
        ).first()

    def list_for_org(self, organisation_id: int) -> list[Team]:
        return list(
            self.session.exec(select(Team).where(Team.organisation_id == organisation_id).order_by(col(Team.name))).all()
        )

    def list_for_user(self, organisation_id: int, user_id: int) -> list[Team]:
        return list(
            self.session.exec(
                select(Team)
                .join(TeamMember, col(TeamMember.team_id) == col(Team.id))
                .where(
                    Team.organisation_id == organisation_id,
                    TeamMember.user_id == user_id,
                    col(TeamMember.left_at).is_(None),
                )
                .order_by(col(Team.name))
            ).all()
        )

    # -- membership -------------------------------------------------------
    def membership(self, team_id: int, user_id: int) -> TeamMember | None:
        """The row for this person, whether or not they are still on the team."""
        return self.session.exec(
            select(TeamMember).where(TeamMember.team_id == team_id, TeamMember.user_id == user_id)
        ).first()

    def active_role(self, team_id: int, user_id: int) -> TeamRole | None:
        row = self.membership(team_id, user_id)
        return row.role if row and row.left_at is None else None

    def active_members(self, team_id: int) -> list[tuple[TeamMember, User]]:
        return list(
            self.session.exec(
                select(TeamMember, User)
                .join(User, col(User.id) == col(TeamMember.user_id))
                .where(TeamMember.team_id == team_id, col(TeamMember.left_at).is_(None))
                .order_by(col(TeamMember.role), col(User.name))
            ).all()
        )

    def lead_count(self, team_id: int) -> int:
        return self.session.exec(
            select(func.count(col(TeamMember.id))).where(
                TeamMember.team_id == team_id, TeamMember.role == TeamRole.LEAD, col(TeamMember.left_at).is_(None)
            )
        ).one()

    def deactivate_user_in_org(self, organisation_id: int, user_id: int) -> int:
        team_ids = select(Team.id).where(Team.organisation_id == organisation_id)
        rows = self.session.exec(
            select(TeamMember).where(
                col(TeamMember.team_id).in_(team_ids), TeamMember.user_id == user_id, col(TeamMember.left_at).is_(None)
            )
        ).all()
        for row in rows:
            row.left_at = utcnow()
            self.session.add(row)
        self.session.flush()
        return len(rows)

    # -- grouped stats used by the team list -----------------------------
    def member_counts(self, team_ids: list[int]) -> dict[int, int]:
        if not team_ids:
            return {}
        rows = self.session.exec(
            select(TeamMember.team_id, func.count(col(TeamMember.id)))
            .where(col(TeamMember.team_id).in_(team_ids), col(TeamMember.left_at).is_(None))
            .group_by(TeamMember.team_id)
        ).all()
        return {team_id: count for team_id, count in rows}

    def leads(self, team_ids: list[int]) -> dict[int, list[tuple[int, str]]]:
        result: dict[int, list[tuple[int, str]]] = {}
        if not team_ids:
            return result
        rows = self.session.exec(
            select(TeamMember.team_id, User.id, User.name)
            .join(User, col(User.id) == col(TeamMember.user_id))
            .where(
                col(TeamMember.team_id).in_(team_ids),
                TeamMember.role == TeamRole.LEAD,
                col(TeamMember.left_at).is_(None),
            )
            .order_by(col(User.name))
        ).all()
        for team_id, user_id, name in rows:
            result.setdefault(team_id, []).append((user_id, name))
        return result

    def todo_counts(self, team_ids: list[int]) -> dict[int, tuple[int, int]]:
        """(open, overdue) todo counts per team."""
        if not team_ids:
            return {}
        now = utcnow()
        rows = self.session.exec(
            select(Task.team_id, Todo.progress, Todo.due)
            .join(Todo, col(Todo.task_id) == col(Task.id))
            .where(col(Task.team_id).in_(team_ids), Todo.progress != Status.COMPLETED)
        ).all()
        counts: dict[int, list[int]] = {}
        for team_id, _progress, due in rows:
            entry = counts.setdefault(team_id, [0, 0])
            entry[0] += 1
            if due is not None and due < now:
                entry[1] += 1
        return {team_id: (open_, late) for team_id, (open_, late) in counts.items()}

    def my_roles(self, team_ids: list[int], user_id: int) -> dict[int, TeamRole]:
        if not team_ids:
            return {}
        rows = self.session.exec(
            select(TeamMember.team_id, TeamMember.role).where(
                col(TeamMember.team_id).in_(team_ids),
                TeamMember.user_id == user_id,
                col(TeamMember.left_at).is_(None),
            )
        ).all()
        return {team_id: role for team_id, role in rows}

    def delete_members(self, team_id: int) -> None:
        for row in self.session.exec(select(TeamMember).where(TeamMember.team_id == team_id)).all():
            self.session.delete(row)
        self.session.flush()
