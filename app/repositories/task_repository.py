from sqlmodel import col, func, select

from app.repositories.base import BaseRepository
from app.schemas.models.enums.status import Status
from app.schemas.models.organisation import OrganisationMember
from app.schemas.models.enums.status import MembershipStatus
from app.schemas.models.task import Task
from app.schemas.models.team import Team
from app.schemas.models.todo import Todo
from app.schemas.models.organisation import Organisation
from app.schemas.models.user import User


class TaskRepository(BaseRepository):
    def get(self, task_id: int) -> Task | None:
        return self.session.get(Task, task_id)

    def find_by_title(self, team_id: int, title: str) -> Task | None:
        return self.session.exec(
            select(Task).where(Task.team_id == team_id, func.lower(Task.title) == title.lower())
        ).first()

    def list_for_team(self, team_id: int) -> list[Task]:
        return list(self.session.exec(select(Task).where(Task.team_id == team_id).order_by(col(Task.created_at))).all())

    def todo_counts(self, task_ids: list[int]) -> dict[int, tuple[int, int]]:
        """(total, done) per task."""
        if not task_ids:
            return {}
        rows = self.session.exec(
            select(Todo.task_id, Todo.progress).where(col(Todo.task_id).in_(task_ids))
        ).all()
        counts: dict[int, list[int]] = {}
        for task_id, progress in rows:
            entry = counts.setdefault(task_id, [0, 0])
            entry[0] += 1
            if progress == Status.COMPLETED:
                entry[1] += 1
        return {task_id: (total, done) for task_id, (total, done) in counts.items()}


class TodoRepository(BaseRepository):
    def get(self, todo_id: int) -> Todo | None:
        return self.session.get(Todo, todo_id)

    def list_for_team(self, team_id: int) -> list[tuple[Todo, Task, User | None]]:
        rows = self.session.exec(
            select(Todo, Task, User)
            .join(Task, col(Task.id) == col(Todo.task_id))
            .join(User, col(User.id) == col(Todo.assigned_to_id), isouter=True)
            .where(Task.team_id == team_id)
            .order_by(col(Todo.created_at), col(Todo.id))
        ).all()
        return list(rows)

    def one_with_context(self, todo_id: int) -> tuple[Todo, Task, User | None] | None:
        return self.session.exec(
            select(Todo, Task, User)
            .join(Task, col(Task.id) == col(Todo.task_id))
            .join(User, col(User.id) == col(Todo.assigned_to_id), isouter=True)
            .where(Todo.id == todo_id)
        ).first()

    def for_user(self, user_id: int) -> list[tuple[Todo, Task, Team, Organisation]]:
        """Everything assigned to this person, across every organisation they currently belong to."""
        rows = self.session.exec(
            select(Todo, Task, Team, Organisation)
            .join(Task, col(Task.id) == col(Todo.task_id))
            .join(Team, col(Team.id) == col(Task.team_id))
            .join(Organisation, col(Organisation.id) == col(Team.organisation_id))
            .join(
                OrganisationMember,
                (col(OrganisationMember.organisation_id) == col(Organisation.id))
                & (col(OrganisationMember.user_id) == user_id)
                & (col(OrganisationMember.status) == MembershipStatus.ACTIVE),
            )
            .where(Todo.assigned_to_id == user_id)
            .order_by(col(Todo.due).is_(None), col(Todo.due), col(Todo.id))
        ).all()
        return list(rows)

    def todos_in_team_for_user(self, team_id: int, user_id: int) -> list[Todo]:
        return list(
            self.session.exec(
                select(Todo)
                .join(Task, col(Task.id) == col(Todo.task_id))
                .where(Task.team_id == team_id, Todo.assigned_to_id == user_id, Todo.progress != Status.COMPLETED)
            ).all()
        )

    def todos_in_org_for_user(self, organisation_id: int, user_id: int) -> list[Todo]:
        return list(
            self.session.exec(
                select(Todo)
                .join(Task, col(Task.id) == col(Todo.task_id))
                .join(Team, col(Team.id) == col(Task.team_id))
                .where(
                    Team.organisation_id == organisation_id,
                    Todo.assigned_to_id == user_id,
                    Todo.progress != Status.COMPLETED,
                )
            ).all()
        )

    def delete_for_task(self, task_id: int) -> None:
        for todo in self.session.exec(select(Todo).where(Todo.task_id == task_id)).all():
            self.session.delete(todo)
        self.session.flush()
