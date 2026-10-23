from fastapi import APIRouter, status

from app.dependencies import Membership, TaskServiceDep
from app.schemas.requests.task_requests import (
    ChangeStatusRequest,
    CreateTaskRequest,
    CreateTodoRequest,
    UpdateTaskRequest,
    UpdateTodoRequest,
)
from app.schemas.responses.responses import TaskOut, TodoOut

router = APIRouter(prefix="/api/orgs/{org_id}", tags=["tasks"])


@router.get("/teams/{team_id}/tasks", response_model=list[TaskOut])
def list_tasks(team_id: int, membership: Membership, service: TaskServiceDep):
    return service.list_tasks(membership, team_id)


@router.post("/teams/{team_id}/tasks", response_model=TaskOut, status_code=status.HTTP_201_CREATED)
def create_task(team_id: int, body: CreateTaskRequest, membership: Membership, service: TaskServiceDep):
    return service.create_task(membership, team_id, body)


@router.get("/teams/{team_id}/todos", response_model=list[TodoOut])
def list_todos(team_id: int, membership: Membership, service: TaskServiceDep):
    return service.list_todos(membership, team_id)


@router.patch("/tasks/{task_id}", response_model=TaskOut)
def update_task(task_id: int, body: UpdateTaskRequest, membership: Membership, service: TaskServiceDep):
    return service.update_task(membership, task_id, body)


@router.delete("/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(task_id: int, membership: Membership, service: TaskServiceDep):
    service.delete_task(membership, task_id)


@router.post("/tasks/{task_id}/todos", response_model=TodoOut, status_code=status.HTTP_201_CREATED)
def create_todo(task_id: int, body: CreateTodoRequest, membership: Membership, service: TaskServiceDep):
    return service.create_todo(membership, task_id, body)


@router.patch("/todos/{todo_id}", response_model=TodoOut)
def update_todo(todo_id: int, body: UpdateTodoRequest, membership: Membership, service: TaskServiceDep):
    return service.update_todo(membership, todo_id, body)


@router.post("/todos/{todo_id}/status", response_model=TodoOut)
def change_status(todo_id: int, body: ChangeStatusRequest, membership: Membership, service: TaskServiceDep):
    return service.change_status(membership, todo_id, body.status)


@router.delete("/todos/{todo_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_todo(todo_id: int, membership: Membership, service: TaskServiceDep):
    service.delete_todo(membership, todo_id)
