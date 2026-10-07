# School Management System

Multi-tenant school ERP with a Django REST API and a React/Vite frontend.

## Codebase map

| Path | Purpose |
| --- | --- |
| `backend/config/` | Django settings, URL routing, ASGI/WSGI entry points |
| `backend/apps/` | Domain modules: accounts and schools, academics, operations, finance, reporting, and platform administration |
| `backend/apps/*/migrations/` | Database schema and data migration history; keep these in order |
| `frontend/src/App.jsx` | Client routes and application shell |
| `frontend/src/pages/` | Screens for the school and platform modules |
| `frontend/src/api.js`, `frontend/src/schoolContext.jsx` | API transport, authentication, and active school context |
| `frontend/tests/` | Frontend regression tests |
| `e2e/` | Playwright browser tests |
| `docs/` | Product and technical documentation |

## Run locally

Requirements: Python 3.12+, Node.js, and PostgreSQL. Copy
`backend/.env.example` to `backend/.env` and set `DJANGO_SECRET_KEY` plus
the database values. `docker compose up -d db` starts the local database
defined in `docker-compose.yml`.

```bash
cd backend
python -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python manage.py migrate
.venv/bin/python manage.py runserver 127.0.0.1:8000
```

In a second terminal:

```bash
cd frontend
npm ci
npm run dev -- --host 127.0.0.1
```

Open `http://127.0.0.1:5173/`. The Vite dev server proxies `/api` to
`http://127.0.0.1:8000`. The API health endpoint is `/api/health/`; add
`?probe=db` to check database connectivity. API documentation is at
`/api/docs/` on the backend.

## Checks

```bash
cd frontend && npm run lint && npm test && npm run build
```

```bash
cd backend
DJANGO_SECRET_KEY=local-test-secret DATABASE_URL=sqlite:///:memory: \
  DJANGO_SETTINGS_MODULE=config.settings.test .venv/bin/python manage.py check
DJANGO_SECRET_KEY=local-test-secret DATABASE_URL=sqlite:///:memory: \
  DJANGO_SETTINGS_MODULE=config.settings.test .venv/bin/python manage.py test apps --noinput
```

The Django test settings use SQLite in memory and do not require a running
PostgreSQL server. For a PostgreSQL run, use
`DJANGO_SETTINGS_MODULE=config.settings.postgres_test` with the database
variables from `backend/.env.example`. Production configuration and setup
details are in `LAUNCH.md` and `ONBOARDING.md`.
