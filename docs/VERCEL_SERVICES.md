# Vercel Services deployment

The repository root is the Vercel project root. Set the project's Framework
Preset to **Services** and deploy with the root `vercel.json`. The two services
are built from `backend/` (Django) and `frontend/` (Vite).

The public routes are:

| Path | Service |
| --- | --- |
| `/api/*` | Django |
| `/admin/*` | Django admin |
| `/static/*` | Django static files |
| `/media/*` | Django media views |
| Everything else | React/Vite frontend |

The frontend makes browser requests to same-origin `/api/*` URLs. It has no
server-side function that calls Django, so no service binding is needed. The
Vite proxy in `frontend/vite.config.js` is for running Vite separately from
Django during development; `vercel dev -L` uses the root routes. Set
`LOCAL_DJANGO_URL` if a standalone Django development server uses a different
host or port.

Set the following in the Vercel project environment (Django reads them):

- `DJANGO_SECRET_KEY`: a secure secret, required to import production settings.
- `DATABASE_URL`: a persistent PostgreSQL connection string. The existing
  `DB_*` settings are an alternative.
- `DJANGO_ALLOWED_HOSTS`: any custom project domains. Vercel preview hosts
  under `.vercel.app` are already allowed.
- `DJANGO_CSRF_TRUSTED_ORIGINS`: each custom public origin (including `https://`).
- `BLOB_READ_WRITE_TOKEN`: required if media uploads must persist on Vercel.

Do not put these secrets in `vercel.json`. Apply Django migrations to the
persistent database as an explicit release step; the build only compiles the
apps and collects static assets. Vercel's Django preset handles `collectstatic`.

For local testing, use a recent Vercel CLI and run `vercel dev -L` from the
repository root. A local `backend/.env` can provide Django and database
settings. Visit `/api/health/`, `/admin/`, and a React route such as `/login`.
