from sqlmodel import Session

from app.core.time import utcnow
from app.exceptions.exception import BadRequestError, ConflictError, ForbiddenError, NotFoundError
from app.repositories.organisation_repository import AuditRepository
from app.repositories.task_repository import TaskRepository, TodoRepository
from app.repositories.team_repository import TeamRepository
from app.repositories.user_repository import UserRepository
from app.schemas.models.enums.status import Status
from app.schemas.models.organisation import OrganisationMember
from app.schemas.models.task import Task
from app.schemas.models.team import Team
from app.schemas.models.todo import Todo
from app.schemas.models.user import User
from app.schemas.requests.task_requests import (
    CreateTaskRequest,
    CreateTodoRequest,
    UpdateTaskRequest,
    UpdateTodoRequest,
)
from app.schemas.responses.responses import MyTodoOut, TaskOut, TodoOut
from app.services.access import AccessControl

# What the person a todo is assigned to may do on their own. Anything else needs the team lead or an admin.
# Notably, only a lead/admin can mark work Completed: that is the review step.
ASSIGNEE_MOVES = {
    (Status.TODO, Status.IN_PROGRESS),
    (Status.IN_PROGRESS, Status.TODO),
    (Status.IN_PROGRESS, Status.IN_REVIEW),
    (Status.IN_REVIEW, Status.IN_PROGRESS),  # withdraw the review request
}


class TaskService:
    def __init__(self, session: Session):
        self.session = session
        self.tasks = TaskRepository(session)
        self.todos = TodoRepository(session)
        self.teams = TeamRepository(session)
        self.audit = AuditRepository(session)
        self.access = AccessControl(session)

    # -- tasks ----------------------------------------------------------------
    def list_tasks(self, actor: OrganisationMember, team_id: int) -> list[TaskOut]:
        team = self.access.team_for(actor, team_id)
        self.access.require_view(actor, team)
        tasks = self.tasks.list_for_team(team.id)
        counts = self.tasks.todo_counts([t.id for t in tasks])
        return [self._task_out(t, counts.get(t.id, (0, 0))) for t in tasks]

    def create_task(self, actor: OrganisationMember, team_id: int, request: CreateTaskRequest) -> TaskOut:
        team = self.access.team_for(actor, team_id)
        self.access.require_manage(actor, team)
        if self.tasks.find_by_title(team.id, request.title):
            raise ConflictError("This team already has a task with that title.", "task_title_taken")
        task = self.tasks.add(
            Task(
                team_id=team.id,
                title=request.title,
                description=(request.description or "").strip() or None,
                due_date=request.due_date,
                created_by_id=actor.user_id,
            )
        )
        self.audit.log(actor.organisation_id, actor.user_id, "task.created", "task", task.id, f"{task.title} ({team.name})")
        self.session.commit()
        return self._task_out(task, (0, 0))

    def update_task(self, actor: OrganisationMember, task_id: int, request: UpdateTaskRequest) -> TaskOut:
        task, team = self._load_task(actor, task_id)
        self.access.require_manage(actor, team)
        if request.title is not None and request.title.lower() != task.title.lower():
            if self.tasks.find_by_title(team.id, request.title):
                raise ConflictError("This team already has a task with that title.", "task_title_taken")
        if request.title is not None:
            task.title = request.title
        if request.description is not None:
            task.description = request.description.strip() or None
        if request.clear_due_date:
            task.due_date = None
        elif request.due_date is not None:
            task.due_date = request.due_date
        task.updated_at = utcnow()
        self.session.add(task)
        self.session.commit()
        return self._task_out(task, self.tasks.todo_counts([task.id]).get(task.id, (0, 0)))

    def delete_task(self, actor: OrganisationMember, task_id: int) -> None:
        task, team = self._load_task(actor, task_id)
        self.access.require_manage(actor, team)
        title = task.title
        self.todos.delete_for_task(task.id)
        self.tasks.delete(task)
        self.audit.log(actor.organisation_id, actor.user_id, "task.deleted", "task", task_id, f"{title} ({team.name})")
        self.session.commit()

    # -- todos ------------------------------------------------------------------
    def list_todos(self, actor: OrganisationMember, team_id: int) -> list[TodoOut]:
        team = self.access.team_for(actor, team_id)
        self.access.require_view(actor, team)
        return [self._todo_out(todo, task, assignee) for todo, task, assignee in self.todos.list_for_team(team.id)]

    def my_todos(self, user: User) -> list[MyTodoOut]:
        result = []
        for todo, task, team, organisation in self.todos.for_user(user.id):
            base = self._todo_out(todo, task, user)
            result.append(
                MyTodoOut(
                    **base.model_dump(),
                    organisation_id=organisation.id,
                    organisation_name=organisation.name,
                    team_name=team.name,
                )
            )
        return result

    def create_todo(self, actor: OrganisationMember, task_id: int, request: CreateTodoRequest) -> TodoOut:
        task, team = self._load_task(actor, task_id)
        self.access.require_manage(actor, team)
        assignee = self._check_assignee(team, request.assigned_to_id)
        todo = self.todos.add(
            Todo(
                task_id=task.id,
                title=request.title,
                description=(request.description or "").strip() or None,
                assigned_to_id=request.assigned_to_id,
                priority=request.priority,
                due=request.due,
                created_by_id=actor.user_id,
            )
        )
        self.audit.log(actor.organisation_id, actor.user_id, "todo.created", "todo", todo.id, f"{todo.title} ({team.name})")
        self.session.commit()
        return self._todo_out(todo, task, assignee)

    def update_todo(self, actor: OrganisationMember, todo_id: int, request: UpdateTodoRequest) -> TodoOut:
        todo, task, team = self._load_todo(actor, todo_id)
        self.access.require_manage(actor, team)
        if request.title is not None:
            todo.title = request.title
        if request.description is not None:
            todo.description = request.description.strip() or None
        if request.priority is not None:
            todo.priority = request.priority
        if request.clear_due:
            todo.due = None
        elif request.due is not None:
            todo.due = request.due
        if request.unassign:
            todo.assigned_to_id = None
        elif request.assigned_to_id is not None:
            self._check_assignee(team, request.assigned_to_id)
            todo.assigned_to_id = request.assigned_to_id
        todo.updated_at = utcnow()
        self.session.add(todo)
        self.session.commit()
        return self._reload(todo.id)

    def change_status(self, actor: OrganisationMember, todo_id: int, new_status: Status) -> TodoOut:
        todo, task, team = self._load_todo(actor, todo_id)
        current = todo.progress
        if new_status == current:
            return self._reload(todo.id)

        is_manager = self.access.can_manage_team(actor, team)
        is_assignee = todo.assigned_to_id == actor.user_id
        if not is_manager:
            if not is_assignee:
                raise ForbiddenError("Only the person assigned to this todo can move it.")
            if (current, new_status) not in ASSIGNEE_MOVES:
                if new_status == Status.COMPLETED:
                    raise ForbiddenError("Send it to review. The team lead marks it completed.", "needs_review")
                raise ForbiddenError("You can't move this todo there. Ask the team lead.")

        todo.progress = new_status
        todo.updated_at = utcnow()
        todo.completed_at = utcnow() if new_status == Status.COMPLETED else None
        self.session.add(todo)

        action = {
            (Status.IN_PROGRESS, Status.IN_REVIEW): "todo.review_requested",
            (Status.IN_REVIEW, Status.COMPLETED): "todo.approved",
            (Status.IN_REVIEW, Status.IN_PROGRESS): "todo.changes_requested" if is_manager and not is_assignee else None,
        }.get((current, new_status))
        if new_status == Status.COMPLETED and current != Status.IN_REVIEW:
            action = "todo.completed"
        if action:
            self.audit.log(actor.organisation_id, actor.user_id, action, "todo", todo.id, f"{todo.title} ({team.name})")
        self.session.commit()
        return self._reload(todo.id)

    def delete_todo(self, actor: OrganisationMember, todo_id: int) -> None:
        todo, _task, team = self._load_todo(actor, todo_id)
        self.access.require_manage(actor, team)
        self.todos.delete(todo)
        self.session.commit()

    # -- helpers --------------------------------------------------------------------
    def _load_task(self, actor: OrganisationMember, task_id: int) -> tuple[Task, Team]:
        task = self.tasks.get(task_id)
        team = self.teams.get(task.team_id) if task else None
        if task is None or team is None or team.organisation_id != actor.organisation_id:
            raise NotFoundError("Task not found.")
        return task, team

    def _load_todo(self, actor: OrganisationMember, todo_id: int) -> tuple[Todo, Task, Team]:
        todo = self.todos.get(todo_id)
        task = self.tasks.get(todo.task_id) if todo else None
        team = self.teams.get(task.team_id) if task else None
        if todo is None or task is None or team is None or team.organisation_id != actor.organisation_id:
            raise NotFoundError("Todo not found.")
        return todo, task, team

    def _check_assignee(self, team: Team, user_id: int | None) -> User | None:
        if user_id is None:
            return None
        if self.teams.active_role(team.id, user_id) is None:
            raise BadRequestError("Todos can only be assigned to people on this team.")
        return UserRepository(self.session).get(user_id)

    def _reload(self, todo_id: int) -> TodoOut:
        row = self.todos.one_with_context(todo_id)
        return self._todo_out(*row)

    @staticmethod
    def _task_out(task: Task, counts: tuple[int, int]) -> TaskOut:
        return TaskOut(
            id=task.id,
            team_id=task.team_id,
            title=task.title,
            description=task.description,
            due_date=task.due_date,
            created_at=task.created_at,
            todo_count=counts[0],
            done_count=counts[1],
        )

    @staticmethod
    def _todo_out(todo: Todo, task: Task, assignee: User | None) -> TodoOut:
        return TodoOut(
            id=todo.id,
            task_id=task.id,
            task_title=task.title,
            team_id=task.team_id,
            title=todo.title,
            description=todo.description,
            assigned_to_id=todo.assigned_to_id,
            assigned_to_name=assignee.name if assignee else None,
            priority=todo.priority,
            progress=todo.progress,
            due=todo.due,
            is_late=bool(todo.due and todo.due < utcnow() and todo.progress != Status.COMPLETED),
            created_at=todo.created_at,
            updated_at=todo.updated_at,
            completed_at=todo.completed_at,
        )
