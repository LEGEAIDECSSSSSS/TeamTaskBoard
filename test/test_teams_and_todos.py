import pytest


@pytest.fixture
def world(signup, make_org, join_org):
    """Acme: owner Olu, admin Ada, members Lena (leads Platform) and Mo.  Globex: owner Gina, Lena is a plain member."""
    people = {
        "olu": signup("Olu", "olu@example.com"),
        "ada": signup("Ada", "ada@example.com"),
        "lena": signup("Lena", "lena@example.com"),
        "mo": signup("Mo", "mo@example.com"),
        "gina": signup("Gina", "gina@example.com"),
    }
    acme = make_org(people["olu"], "Acme")
    globex = make_org(people["gina"], "Globex")
    join_org(people["olu"], acme, people["ada"], "admin")
    join_org(people["olu"], acme, people["lena"], "member")
    join_org(people["olu"], acme, people["mo"], "member")
    join_org(people["gina"], globex, people["lena"], "member")
    return {"people": people, "acme": acme, "globex": globex}


def make_team(client, org_id, name, lead_id):
    response = client.post(f"/api/orgs/{org_id}/teams", json={"name": name, "lead_user_id": lead_id})
    assert response.status_code == 201, response.text
    return response.json()


def test_only_admins_create_teams_and_the_lead_must_be_in_the_org(world):
    p, acme = world["people"], world["acme"]
    assert p["lena"].post(f"/api/orgs/{acme}/teams", json={"name": "Platform", "lead_user_id": p["lena"].user_id}).status_code == 403
    assert p["ada"].post(f"/api/orgs/{acme}/teams", json={"name": "Platform", "lead_user_id": p["gina"].user_id}).status_code == 400
    team = make_team(p["ada"], acme, "Platform", p["lena"].user_id)
    assert [lead["name"] for lead in team["leads"]] == ["Lena"]
    assert p["ada"].post(f"/api/orgs/{acme}/teams", json={"name": "platform", "lead_user_id": p["lena"].user_id}).status_code == 409


def test_a_team_lead_can_be_an_ordinary_member_of_another_team(world):
    p, acme = world["people"], world["acme"]
    platform = make_team(p["ada"], acme, "Platform", p["lena"].user_id)
    design = make_team(p["ada"], acme, "Design", p["mo"].user_id)
    assert p["ada"].post(f"/api/orgs/{acme}/teams/{design['id']}/members", json={"user_id": p["lena"].user_id}).status_code == 201

    lena = {t["name"]: t["my_role"] for t in p["lena"].get(f"/api/orgs/{acme}/teams").json()}
    assert lena == {"Platform": "lead", "Design": "member"}

    # lead of Platform can manage Platform...
    assert p["lena"].post(f"/api/orgs/{acme}/teams/{platform['id']}/tasks", json={"title": "Ship v1"}).status_code == 201
    # ...but is only a member of Design, so can't manage it
    assert p["lena"].post(f"/api/orgs/{acme}/teams/{design['id']}/tasks", json={"title": "Sneaky"}).status_code == 403
    assert p["lena"].post(f"/api/orgs/{acme}/teams/{design['id']}/members", json={"user_id": p["ada"].user_id}).status_code == 403


def test_members_only_see_their_own_teams_but_admins_see_all(world):
    p, acme = world["people"], world["acme"]
    platform = make_team(p["ada"], acme, "Platform", p["lena"].user_id)
    design = make_team(p["ada"], acme, "Design", p["lena"].user_id)
    assert {t["name"] for t in p["ada"].get(f"/api/orgs/{acme}/teams").json()} == {"Platform", "Design"}
    assert p["mo"].get(f"/api/orgs/{acme}/teams").json() == []
    assert p["mo"].get(f"/api/orgs/{acme}/teams/{platform['id']}").status_code == 403
    assert p["mo"].get(f"/api/orgs/{acme}/teams/{design['id']}/tasks").status_code == 403


def test_team_names_and_task_titles_are_scoped_not_global(world):
    p, acme, globex = world["people"], world["acme"], world["globex"]
    acme_team = make_team(p["ada"], acme, "Platform", p["lena"].user_id)
    globex_team = make_team(p["gina"], globex, "Platform", p["gina"].user_id)  # same name, other org: fine
    other = make_team(p["ada"], acme, "Support", p["mo"].user_id)

    assert p["lena"].post(f"/api/orgs/{acme}/teams/{acme_team['id']}/tasks", json={"title": "Setup"}).status_code == 201
    assert p["lena"].post(f"/api/orgs/{acme}/teams/{acme_team['id']}/tasks", json={"title": "setup"}).status_code == 409
    assert p["gina"].post(f"/api/orgs/{globex}/teams/{globex_team['id']}/tasks", json={"title": "Setup"}).status_code == 201
    assert p["mo"].post(f"/api/orgs/{acme}/teams/{other['id']}/tasks", json={"title": "Setup"}).status_code == 201


def test_data_is_isolated_between_organisations(world):
    p, acme, globex = world["people"], world["acme"], world["globex"]
    team = make_team(p["ada"], acme, "Platform", p["lena"].user_id)
    task = p["lena"].post(f"/api/orgs/{acme}/teams/{team['id']}/tasks", json={"title": "Ship"}).json()
    todo = p["lena"].post(f"/api/orgs/{acme}/tasks/{task['id']}/todos", json={"title": "Do it"}).json()

    # Lena is in both orgs, but an Acme id used inside the Globex URL doesn't resolve
    assert p["lena"].get(f"/api/orgs/{globex}/teams/{team['id']}").status_code == 404
    assert p["lena"].get(f"/api/orgs/{globex}/teams/{team['id']}/todos").status_code == 404
    assert p["lena"].post(f"/api/orgs/{globex}/todos/{todo['id']}/status", json={"status": "in_progress"}).status_code == 404
    assert p["lena"].delete(f"/api/orgs/{globex}/tasks/{task['id']}").status_code == 404
    # and Gina, who is not in Acme, can't reach it at all
    assert p["gina"].get(f"/api/orgs/{acme}/teams/{team['id']}").status_code == 404


def test_only_team_members_can_be_assigned_todos(world):
    p, acme = world["people"], world["acme"]
    team = make_team(p["ada"], acme, "Platform", p["lena"].user_id)
    task = p["lena"].post(f"/api/orgs/{acme}/teams/{team['id']}/tasks", json={"title": "Ship"}).json()
    response = p["lena"].post(
        f"/api/orgs/{acme}/tasks/{task['id']}/todos", json={"title": "Do it", "assigned_to_id": p["mo"].user_id}
    )
    assert response.status_code == 400
    p["lena"].post(f"/api/orgs/{acme}/teams/{team['id']}/members", json={"user_id": p["mo"].user_id})
    assert (
        p["lena"]
        .post(f"/api/orgs/{acme}/tasks/{task['id']}/todos", json={"title": "Do it", "assigned_to_id": p["mo"].user_id})
        .status_code
        == 201
    )


def test_review_workflow(world):
    p, acme = world["people"], world["acme"]
    team = make_team(p["ada"], acme, "Platform", p["lena"].user_id)
    p["lena"].post(f"/api/orgs/{acme}/teams/{team['id']}/members", json={"user_id": p["mo"].user_id})
    task = p["lena"].post(f"/api/orgs/{acme}/teams/{team['id']}/tasks", json={"title": "Ship"}).json()
    todo = p["lena"].post(
        f"/api/orgs/{acme}/tasks/{task['id']}/todos", json={"title": "Write docs", "assigned_to_id": p["mo"].user_id}
    ).json()
    move = lambda who, status: p[who].post(f"/api/orgs/{acme}/todos/{todo['id']}/status", json={"status": status})

    assert todo["progress"] == "todo"
    assert move("mo", "in_progress").status_code == 200
    assert move("mo", "completed").status_code == 403  # assignees can't approve their own work
    assert move("mo", "completed").json()["code"] == "needs_review"
    assert move("mo", "in_review").json()["progress"] == "in_review"
    assert move("mo", "completed").status_code == 403
    assert move("lena", "in_progress").status_code == 200  # lead sends it back
    assert move("mo", "in_review").status_code == 200
    done = move("lena", "completed")
    assert done.json()["progress"] == "completed" and done.json()["completed_at"]
    assert move("mo", "in_progress").status_code == 403  # a finished todo is the lead's to reopen
    assert move("lena", "in_progress").status_code == 200

    actions = [e["action"] for e in p["ada"].get(f"/api/orgs/{acme}/activity").json()]
    for expected in ("todo.review_requested", "todo.approved", "todo.changes_requested"):
        assert expected in actions


def test_only_the_assignee_or_a_manager_can_move_a_todo(world):
    p, acme = world["people"], world["acme"]
    team = make_team(p["ada"], acme, "Platform", p["lena"].user_id)
    p["lena"].post(f"/api/orgs/{acme}/teams/{team['id']}/members", json={"user_id": p["mo"].user_id})
    task = p["lena"].post(f"/api/orgs/{acme}/teams/{team['id']}/tasks", json={"title": "Ship"}).json()
    todo = p["lena"].post(f"/api/orgs/{acme}/tasks/{task['id']}/todos", json={"title": "Docs"}).json()  # unassigned
    assert p["mo"].post(f"/api/orgs/{acme}/todos/{todo['id']}/status", json={"status": "in_progress"}).status_code == 403
    assert p["ada"].post(f"/api/orgs/{acme}/todos/{todo['id']}/status", json={"status": "in_progress"}).status_code == 200  # org admin


def test_overdue_is_derived_not_stored(world):
    p, acme = world["people"], world["acme"]
    team = make_team(p["ada"], acme, "Platform", p["lena"].user_id)
    task = p["lena"].post(f"/api/orgs/{acme}/teams/{team['id']}/tasks", json={"title": "Ship"}).json()
    todo = p["lena"].post(
        f"/api/orgs/{acme}/tasks/{task['id']}/todos", json={"title": "Late", "due": "2020-01-01T09:00:00Z"}
    ).json()
    assert todo["is_late"] is True and todo["due"].endswith("Z")
    assert p["lena"].get(f"/api/orgs/{acme}/teams").json()[0]["overdue_todo_count"] == 1
    done = p["lena"].post(f"/api/orgs/{acme}/todos/{todo['id']}/status", json={"status": "completed"}).json()
    assert done["is_late"] is False


def test_my_work_spans_organisations(world):
    p, acme, globex = world["people"], world["acme"], world["globex"]
    for client, org, lead in ((p["ada"], acme, p["lena"]), (p["gina"], globex, p["gina"])):
        team = make_team(client, org, "Platform", lead.user_id)
        if org == globex:
            p["gina"].post(f"/api/orgs/{globex}/teams/{team['id']}/members", json={"user_id": p["lena"].user_id})
        task = lead.post(f"/api/orgs/{org}/teams/{team['id']}/tasks", json={"title": "Ship"}).json()
        lead.post(f"/api/orgs/{org}/tasks/{task['id']}/todos", json={"title": f"Work in {org}", "assigned_to_id": p["lena"].user_id})
    mine = p["lena"].get("/api/me/todos").json()
    assert {(t["organisation_name"], t["team_name"]) for t in mine} == {("Acme", "Platform"), ("Globex", "Platform")}


def test_last_lead_protection_and_removing_members_releases_their_todos(world):
    p, acme = world["people"], world["acme"]
    team = make_team(p["ada"], acme, "Platform", p["lena"].user_id)
    p["lena"].post(f"/api/orgs/{acme}/teams/{team['id']}/members", json={"user_id": p["mo"].user_id})
    base = f"/api/orgs/{acme}/teams/{team['id']}"
    # the lead can't walk away from (or demote themselves out of) an otherwise leaderless team
    assert p["lena"].delete(f"{base}/members/{p['lena'].user_id}").status_code == 409
    assert p["lena"].patch(f"{base}/members/{p['lena'].user_id}", json={"role": "member"}).status_code == 409
    # promote a second lead, then stepping down is fine
    assert p["lena"].patch(f"{base}/members/{p['mo'].user_id}", json={"role": "lead"}).status_code == 200
    assert p["lena"].patch(f"{base}/members/{p['lena'].user_id}", json={"role": "member"}).status_code == 200

    task = p["mo"].post(f"{base}/tasks", json={"title": "Ship"}).json()
    todo = p["mo"].post(
        f"/api/orgs/{acme}/tasks/{task['id']}/todos", json={"title": "Docs", "assigned_to_id": p["lena"].user_id}
    ).json()
    assert p["mo"].delete(f"{base}/members/{p['lena'].user_id}").status_code == 200
    assert p["mo"].get(f"{base}/todos").json()[0]["assigned_to_id"] is None
    assert p["lena"].get(f"{base}").status_code == 403


def test_deleting_a_team_removes_its_work(world):
    p, acme = world["people"], world["acme"]
    team = make_team(p["ada"], acme, "Platform", p["lena"].user_id)
    task = p["lena"].post(f"/api/orgs/{acme}/teams/{team['id']}/tasks", json={"title": "Ship"}).json()
    p["lena"].post(f"/api/orgs/{acme}/tasks/{task['id']}/todos", json={"title": "Docs", "assigned_to_id": p["lena"].user_id})
    assert p["lena"].delete(f"/api/orgs/{acme}/teams/{team['id']}").status_code == 403
    assert p["ada"].delete(f"/api/orgs/{acme}/teams/{team['id']}").status_code == 204
    assert p["lena"].get("/api/me/todos").json() == []
    assert p["ada"].get(f"/api/orgs/{acme}/teams").json() == []
