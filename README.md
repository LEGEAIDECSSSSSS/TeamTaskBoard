# TaskBoard (Team Task Board / Mini Trello)

A task board for teams that works across **multiple organisations**. One account can own a company, lead a team
in another, and be an ordinary member of a third, and your role in each is independent.

- **Backend:** FastAPI, SQLModel, Alembic (MySQL in production, SQLite for local development)
- **Frontend:** React + Vite (`frontend/`), served by FastAPI in production
- **Auth:** argon2 password hashes, httpOnly cookie sessions with rotating refresh tokens, email verification

## Quick start

```bash
# 1. Backend  (Python 3.12+)
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload          # http://localhost:8000  (API docs at /docs)

# 2. Frontend, in a second terminal  (Node 18+)
cd frontend
npm install
npm run dev                            # http://localhost:5173, proxies /api to :8000
```

Open http://localhost:5173 and register. With the default `EMAIL_BACKEND=console` there is no mail server: the
**verification link is printed in the backend terminal**. Open it, log in, and create an organisation.

### One server for everything (production style)

```bash
cd frontend && npm install && npm run build && cd ..
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

If `frontend/dist` exists, FastAPI serves the app and the API from one origin, so no CORS setup is needed and cookies
just work. Keep the API and the frontend on the same origin: the auth cookies are `SameSite=Lax`.

### Configuration

Copy `.env.example` to `.env`. Everything has a development default. The ones that matter in production:

| Variable | Purpose |
|---|---|
| `TEAM_TASK_BOARD_SCHEMA` | Database URL, e.g. `mysql+pymysql://user:pass@host:3306/task_board_db` |
| `SECRET_KEY` | Signs access tokens. Required when `ENVIRONMENT=production` |
| `ENVIRONMENT` | `production` enables Secure cookies |
| `FRONTEND_URL` | Base URL used in emailed links |
| `EMAIL_BACKEND` + `SMTP_*` | `console` (log) or `smtp` (real email) |
| `AUTO_CREATE_TABLES` | Set `false` once you use Alembic migrations |

**MySQL:** `docker compose up -d` starts a local MySQL 8.4. Then set `TEAM_TASK_BOARD_SCHEMA`, set
`AUTO_CREATE_TABLES=false`, and run `alembic upgrade head`. (Use *either* migrations *or* auto-create, not both.)

## How access works

There is no global "admin" flag and nobody chooses a role when registering. Authority comes from memberships:

**Organisation role** (per person, per organisation):

| | Owner | Admin | Member |
|---|:-:|:-:|:-:|
| Rename organisation, change roles | ✅ | | |
| Invite people | any role | members only | |
| Remove people | anyone but self | regular members | |
| Create / delete teams, appoint leads | ✅ | ✅ | |
| See every team and the activity log | ✅ | ✅ | only their own teams |

**Team role** (per person, per team): a **lead** manages that team's tasks and todos, adds or removes its members, and
approves finished work. A lead of Team A is just a member of Team B unless someone makes them a lead there too.

Rules worth knowing:

- **Creating an organisation makes you its owner.** Joining an existing one is by **invitation only**, matched to the
  invited person's verified email. Invitations carry the role being granted, so roles can't be self-assigned.
- An organisation always keeps at least one owner. A team lead can't step down from a team that would be left with no lead.
- **Changing jobs:** leave an organisation from its Settings (or an admin removes you). You lose access and your team
  memberships there, your open todos become unassigned, and your history stays in the activity log. A new invitation
  brings you back with a clean slate. Your other organisations are untouched.
- **Review flow:** assignees move todos *To do → In progress → In review*. Only a lead or admin moves a todo to
  *Completed* (approve) or sends it back (request changes).
- Overdue isn't a stored status. It's derived from the due date, so it can never go stale.
- Team names and task titles are unique **within** their organisation/team, not globally.

## Project layout

```
app/
  main.py                 app wiring, error handlers, serves frontend/dist
  config/settings.py      settings + database engine
  core/                   password hashing, tokens, rate limiter, time helpers
  controllers/            HTTP routes (thin)
  services/               business rules and permissions (access.py is the single source of "who may")
  repositories/           database queries
  schemas/models/         SQLModel tables; schemas/requests, schemas/responses for the API
migrations/               Alembic (initial schema included)
frontend/src/             React app: pages/, components/, ui/, styles/
test/                     API-level tests (pytest)
```

Data model: `User` (identity only) · `Organisation` · `OrganisationMember` (role per org) · `Invitation` ·
`Team` · `TeamMember` (role per team) · `Task` · `Todo` · `AuditLog` · `AuthToken` · `RefreshSession`.

## Tests

```bash
pytest
```

The suite drives the real API with separate cookie jars per user and covers: email and password validation,
verification and reset flows, session rotation and theft detection, no self-promotion, invitation rules, one person in
several organisations, leaving and rejoining, last-owner protection, leads who are members elsewhere, isolation
between organisations, and the review workflow.

## Honest limitations

- **MySQL is untested in this repository's CI/sandbox.** The migration was generated and applied on SQLite and the code
  avoids dialect-specific features, but run `alembic upgrade head` against a MySQL instance before you rely on it.
- The login/registration rate limiter is in memory (per process). Behind several workers or servers, move it to Redis.
- Sessions use `SameSite=Lax` cookies and JSON-only bodies for CSRF protection; there is no separate CSRF token.
- Not included (good next steps): deleting an organisation, email notifications for assignments, task comments,
  and per-device session management.

## API

Interactive docs are at `/docs` while the server runs. Everything inside an organisation lives under
`/api/orgs/{org_id}/…`, and every such route first checks that you are an **active member of that organisation**.
