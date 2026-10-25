def test_creating_an_organisation_makes_you_its_owner(signup, make_org):
    ada = signup("Ada", "ada@example.com")
    org_id = make_org(ada, "Acme")
    mine = ada.get("/api/me/organisations").json()
    assert [(m["organisation"]["name"], m["role"]) for m in mine] == [("Acme", "owner")]
    assert ada.get(f"/api/orgs/{org_id}").json()["role"] == "owner"


def test_you_cannot_enter_an_organisation_you_were_not_invited_to(signup, make_org):
    ada = signup("Ada", "ada@example.com")
    bob = signup("Bob", "bob@example.com")
    org_id = make_org(ada, "Acme")
    for path in ("", "/members", "/teams", "/invitations", "/activity"):
        assert bob.get(f"/api/orgs/{org_id}{path}").status_code == 404, path


def test_invitation_roles_are_limited_by_who_sends_them(signup, make_org, join_org):
    owner = signup("Olu", "olu@example.com")
    admin = signup("Ada", "ada@example.com")
    member = signup("Mo", "mo@example.com")
    org_id = make_org(owner, "Acme")
    join_org(owner, org_id, admin, "admin")
    join_org(owner, org_id, member, "member")

    # members can't invite anyone
    assert member.post(f"/api/orgs/{org_id}/invitations", json={"email": "x@example.com"}).status_code == 403
    # admins can invite members but can't hand out admin or owner
    assert admin.post(f"/api/orgs/{org_id}/invitations", json={"email": "x@example.com", "role": "admin"}).status_code == 403
    assert admin.post(f"/api/orgs/{org_id}/invitations", json={"email": "x@example.com", "role": "owner"}).status_code == 403
    assert admin.post(f"/api/orgs/{org_id}/invitations", json={"email": "x@example.com", "role": "member"}).status_code == 201
    # owners can invite any role
    assert owner.post(f"/api/orgs/{org_id}/invitations", json={"email": "y@example.com", "role": "admin"}).status_code == 201


def test_nobody_can_promote_themselves(signup, make_org, join_org):
    owner = signup("Olu", "olu@example.com")
    admin = signup("Ada", "ada@example.com")
    member = signup("Mo", "mo@example.com")
    org_id = make_org(owner, "Acme")
    join_org(owner, org_id, admin, "admin")
    join_org(owner, org_id, member, "member")

    assert member.patch(f"/api/orgs/{org_id}/members/{member.user_id}", json={"role": "owner"}).status_code == 403
    assert admin.patch(f"/api/orgs/{org_id}/members/{admin.user_id}", json={"role": "owner"}).status_code == 403
    assert admin.patch(f"/api/orgs/{org_id}/members/{member.user_id}", json={"role": "admin"}).status_code == 403
    assert owner.patch(f"/api/orgs/{org_id}/members/{member.user_id}", json={"role": "admin"}).status_code == 204
    roles = {m["name"]: m["role"] for m in owner.get(f"/api/orgs/{org_id}/members").json()}
    assert roles == {"Olu": "owner", "Ada": "admin", "Mo": "admin"}


def test_an_invitation_only_works_for_the_invited_email(signup, make_org):
    owner = signup("Olu", "olu@example.com")
    stranger = signup("Sam", "sam@example.com")
    org_id = make_org(owner, "Acme")
    invitation = owner.post(f"/api/orgs/{org_id}/invitations", json={"email": "ada@example.com"}).json()
    assert stranger.get("/api/me/invitations").json() == []
    assert stranger.post(f"/api/me/invitations/{invitation['id']}/accept").status_code == 404
    assert stranger.get(f"/api/orgs/{org_id}").status_code == 404


def test_duplicate_and_redundant_invitations_are_refused(signup, make_org, join_org):
    owner = signup("Olu", "olu@example.com")
    ada = signup("Ada", "ada@example.com")
    org_id = make_org(owner, "Acme")
    first = owner.post(f"/api/orgs/{org_id}/invitations", json={"email": "ada@example.com"})
    assert first.status_code == 201
    assert owner.post(f"/api/orgs/{org_id}/invitations", json={"email": "ada@example.com"}).status_code == 409
    ada.post(f"/api/me/invitations/{first.json()['id']}/accept")
    assert owner.post(f"/api/orgs/{org_id}/invitations", json={"email": "ada@example.com"}).status_code == 409


def test_invitations_can_be_revoked_or_declined(signup, make_org):
    owner = signup("Olu", "olu@example.com")
    ada = signup("Ada", "ada@example.com")
    org_id = make_org(owner, "Acme")
    inv = owner.post(f"/api/orgs/{org_id}/invitations", json={"email": "ada@example.com"}).json()
    assert owner.delete(f"/api/orgs/{org_id}/invitations/{inv['id']}").status_code == 204
    assert ada.post(f"/api/me/invitations/{inv['id']}/accept").status_code == 400

    inv2 = owner.post(f"/api/orgs/{org_id}/invitations", json={"email": "ada@example.com"}).json()
    assert ada.post(f"/api/me/invitations/{inv2['id']}/decline").status_code == 204
    assert ada.get("/api/me/invitations").json() == []


def test_one_person_can_belong_to_several_organisations_with_different_roles(signup, make_org, join_org):
    ada = signup("Ada", "ada@example.com")
    boss = signup("Bola", "bola@example.com")
    acme = make_org(ada, "Acme")  # Ada owns this one
    globex = make_org(boss, "Globex")
    join_org(boss, globex, ada, "member")  # ...and is just a member here

    mine = {m["organisation"]["name"]: m["role"] for m in ada.get("/api/me/organisations").json()}
    assert mine == {"Acme": "owner", "Globex": "member"}

    # authority does not leak across organisations
    assert ada.post(f"/api/orgs/{acme}/teams", json={"name": "Platform", "lead_user_id": ada.user_id}).status_code == 201
    assert ada.post(f"/api/orgs/{globex}/teams", json={"name": "Platform", "lead_user_id": ada.user_id}).status_code == 403
    assert ada.post(f"/api/orgs/{globex}/invitations", json={"email": "z@example.com"}).status_code == 403


def test_last_owner_cannot_leave_or_step_down(signup, make_org, join_org):
    owner = signup("Olu", "olu@example.com")
    ada = signup("Ada", "ada@example.com")
    org_id = make_org(owner, "Acme")
    join_org(owner, org_id, ada, "admin")

    assert owner.post(f"/api/orgs/{org_id}/leave").status_code == 409
    assert owner.patch(f"/api/orgs/{org_id}/members/{owner.user_id}", json={"role": "admin"}).status_code == 409
    # hand over ownership, then leaving is fine
    assert owner.patch(f"/api/orgs/{org_id}/members/{ada.user_id}", json={"role": "owner"}).status_code == 204
    assert owner.post(f"/api/orgs/{org_id}/leave").status_code == 204
    assert owner.get(f"/api/orgs/{org_id}").status_code == 404
    assert ada.get(f"/api/orgs/{org_id}").json()["role"] == "owner"


def test_removal_rules(signup, make_org, join_org):
    owner = signup("Olu", "olu@example.com")
    admin = signup("Ada", "ada@example.com")
    other_admin = signup("Ade", "ade@example.com")
    member = signup("Mo", "mo@example.com")
    org_id = make_org(owner, "Acme")
    for person, role in ((admin, "admin"), (other_admin, "admin"), (member, "member")):
        join_org(owner, org_id, person, role)

    assert member.delete(f"/api/orgs/{org_id}/members/{admin.user_id}").status_code == 403
    assert admin.delete(f"/api/orgs/{org_id}/members/{owner.user_id}").status_code == 403
    assert admin.delete(f"/api/orgs/{org_id}/members/{other_admin.user_id}").status_code == 403
    assert admin.delete(f"/api/orgs/{org_id}/members/{admin.user_id}").status_code == 400  # use leave
    assert admin.delete(f"/api/orgs/{org_id}/members/{member.user_id}").status_code == 204
    assert member.get(f"/api/orgs/{org_id}").status_code == 404
    assert owner.delete(f"/api/orgs/{org_id}/members/{other_admin.user_id}").status_code == 204


def test_leaving_releases_work_and_rejoining_starts_fresh(signup, make_org, join_org):
    owner = signup("Olu", "olu@example.com")
    ada = signup("Ada", "ada@example.com")
    org_id = make_org(owner, "Acme")
    join_org(owner, org_id, ada, "member")
    team = owner.post(f"/api/orgs/{org_id}/teams", json={"name": "Platform", "lead_user_id": owner.user_id}).json()
    owner.post(f"/api/orgs/{org_id}/teams/{team['id']}/members", json={"user_id": ada.user_id})
    task = owner.post(f"/api/orgs/{org_id}/teams/{team['id']}/tasks", json={"title": "Launch"}).json()
    todo = owner.post(
        f"/api/orgs/{org_id}/tasks/{task['id']}/todos", json={"title": "Write docs", "assigned_to_id": ada.user_id}
    ).json()
    assert [t["id"] for t in ada.get("/api/me/todos").json()] == [todo["id"]]

    assert ada.post(f"/api/orgs/{org_id}/leave").status_code == 204
    # their open work is released, they lose access, history stays in the activity log
    assert ada.get("/api/me/todos").json() == []
    assert ada.get(f"/api/orgs/{org_id}/teams").status_code == 404
    todos = owner.get(f"/api/orgs/{org_id}/teams/{team['id']}/todos").json()
    assert todos[0]["assigned_to_id"] is None
    assert owner.get(f"/api/orgs/{org_id}/teams/{team['id']}").json()["member_count"] == 1
    actions = [e["action"] for e in owner.get(f"/api/orgs/{org_id}/activity").json()]
    assert "member.left" in actions

    # coming back (a new job at the same company) goes through a new invitation and a clean slate
    join_org(owner, org_id, ada, "member")
    assert ada.get(f"/api/orgs/{org_id}/teams").json() == []  # not automatically back on any team
    members = owner.get(f"/api/orgs/{org_id}/members").json()
    assert [m["name"] for m in members].count("Ada") == 1


def test_activity_log_is_for_admins_only(signup, make_org, join_org):
    owner = signup("Olu", "olu@example.com")
    member = signup("Mo", "mo@example.com")
    org_id = make_org(owner, "Acme")
    join_org(owner, org_id, member)
    assert member.get(f"/api/orgs/{org_id}/activity").status_code == 403
    assert owner.get(f"/api/orgs/{org_id}/activity").status_code == 200


def test_only_owners_can_rename(signup, make_org, join_org):
    owner = signup("Olu", "olu@example.com")
    admin = signup("Ada", "ada@example.com")
    org_id = make_org(owner, "Acme")
    join_org(owner, org_id, admin, "admin")
    assert admin.patch(f"/api/orgs/{org_id}", json={"name": "Hacked"}).status_code == 403
    assert owner.patch(f"/api/orgs/{org_id}", json={"name": "Acme Ltd"}).json()["organisation"]["name"] == "Acme Ltd"
