# Deployment Guide

> This guide describes the older Vercel + Render deployment and references a
> frontend Vercel config that was removed. For the current one-project setup,
> use [Vercel Services](VERCEL_SERVICES.md).

The app is split in two:

- **Frontend** (React + Vite, in `frontend/`) -> **Vercel**
- **Backend** (Django, in `backend/`) -> **Render** (Docker web service)
- **Database** -> **Neon** (free Postgres, no credit card, no 30-day expiry)

The frontend calls `/api/*` as a relative URL. On Vercel,
`frontend/vercel.json` rewrites `/api/*` to the Render backend, so cookies
stay **same-site** and the existing session/CSRF flow works unchanged.

> Why not Render's managed Postgres? It requires a credit card and the free
> tier expires after 30 days. Neon's free tier needs no card and does not
> expire, and `?sslmode=require` in the connection string works with the
> existing `dj_database_url` setup unchanged.

## Before you start (checklist)

- [ ] Repo pushed to GitHub
- [ ] A **Neon** account and a project/database created (free, no card)
- [ ] The Neon connection string added privately in Render as
  `DATABASE_URL` (never commit it to `render.yaml`)
- [ ] `render.yaml` `repo:` points at your actual GitHub repo
      (already set to `lordvalicious/perfect-foundation-sms`)
- [ ] `render.yaml` `DJANGO_CSRF_TRUSTED_ORIGINS` matches your Vercel URL
- [ ] After the backend deploys: copy its `https://*.onrender.com` URL into
      `frontend/vercel.json` (see step 3 below)

---

## 1. Prerequisites

- The repo pushed to GitHub (e.g. `github.com/you/perfect-foundation-sms`)
- A [Vercel](https://vercel.com) account
- A [Render](https://render.com) account
- A [Neon](https://neon.tech) account

## 2. Set up the database (Neon)

1. Sign up at https://neon.tech (free, **no credit card required**).
2. Click **Create a project** (region: any, e.g. `US East`) - a database
   named `neondb` is created for you.
3. Go to **Connect** and copy the **Connection string** (URI). It looks like:
   `postgresql://user:pass@ep-xxx.us-east-1.aws.neon.tech/neondb?sslmode=require`
   (Neon includes `?sslmode=require`; keep it - the app needs SSL.)
4. In Render Dashboard -> Environment, add `DATABASE_URL` as a secret and
  paste the Neon connection string there. Do not add it to `render.yaml`
  or commit it to GitHub, then redeploy the service.

## 3. Deploy the backend on Render

1. Open the blueprint directly (skips the dashboard menu; `render.yaml`
   must be at the repo root, which it is):
   `https://dashboard.render.com/blueprint/new?repo=https://github.com/lordvalicious/perfect-foundation-sms`
   (or in the dashboard: **New -> Blueprint**, connect your repo).
   Render provisions only:

   - `perfect-foundation-backend` (Docker web service, **free plan**)

   No managed Postgres, so **no credit card** is required.

   Make sure the plan is `Free` in the creation screen before you click
   Create. The blueprint runs `sh ./startup.sh` before every deploy, which
   applies migrations and collects static files.

2. After the first successful deploy, the service URL will look like
   `https://perfect-foundation-backend.onrender.com`. Verify it:
   `curl https://perfect-foundation-backend.onrender.com/api/health/`

### Backend environment

The blueprint sets most variables automatically:

| Variable | Source |
| --- | --- |
| `DJANGO_SETTINGS_MODULE` | `config.settings.production` |
| `DJANGO_SECRET_KEY` | auto-generated (set once) |
| `DJANGO_ALLOWED_HOSTS` | `*` (tighten after adding a custom domain) |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | your Vercel origin, edit if you change it |
| `DATABASE_URL` | your Neon connection string |

### Create an admin user

The production database starts empty. From the Render dashboard, open
**Shell** for the backend service and run:

```sh
python manage.py createsuperuser
```

### Optional: migrate your local data

To copy your local Postgres data to the production database:

```sh
docker compose exec db pg_dump -U school_admin perfect_foundation > dump.sql
# then in the Render shell:
cat dump.sql | python manage.py dbshell
```

(Simpler: use Render's dashboard DB import, or `pg_restore` from a
`pg_dump -Fc` archive.)

## 4. Deploy the frontend on Vercel

1. Vercel -> **Add New -> Project**, import the repo.
2. Project settings:
   - Framework preset: **Vite**
   - Root directory: `frontend`
   - Build command: `npm run build`
   - Output directory: `dist`
3. After deploy, edit `frontend/vercel.json` so `/api` rewrites point at your
   real Render URL, then redeploy:

   ```json
   {
     "rewrites": [
       { "source": "/api/:path*", "destination": "https://perfect-foundation-backend.onrender.com/api/:path*" },
       { "source": "/(.*)", "destination": "/index.html" }
     ]
   }
   ```

4. Visit your Vercel URL and sign in with the admin you created.

## 5. Custom domain (recommended)

- Vercel: add your domain to the frontend project.
- Render: add the same domain to the backend service (Settings -> Custom
  Domain), then update `DJANGO_ALLOWED_HOSTS` and
  `DJANGO_CSRF_TRUSTED_ORIGINS` to the real domains (they already include
  your Vercel origin).

## 6. Operations: CSP violation retention

CSP violation reports are sanitized and stored in the `CSPViolation` table.
Records are retained for **90 days** by default and must be purged on a
schedule to keep the table bounded.

### Cleanup command

```sh
python manage.py cleanup_csp_violations --days=90
```

- **Purpose:** delete `CSPViolation` records older than the retention period.
- **Default retention:** `90` days (see `--days` help).
- **Override:** `--days=<N>` sets a custom retention period; `--days` must be
  a positive integer (`0` and negative values are rejected to prevent
  accidental full-table deletion).
- **Deletion predicate:** `timestamp < now - retention` (timezone-aware,
  using the record's authoritative received timestamp). Single database-side
  queryset delete — records are never loaded into Python.
- **Safety:** time-based only (never by user/institution/IP/directive); safe
  to run repeatedly; safe with zero matching records; deletes across **all**
  institutions. Output is an operational count only — no report payloads,
  IPs, user agents, or URLs are printed.
- **Scheduling responsibility:** the Vercel serverless backend has no
  persistent shell and Vercel Cron can only invoke HTTP endpoints. A cleanup
  HTTP endpoint is intentionally **not** exposed. Management command
  implemented; production scheduling remains an operational responsibility —
  run the command from any host with access to the production Django
  environment (external cron, CI, or manual operator run).

## Notes / limitations

- **Neon free tier**: 0.5 GB storage, no expiry, and the database sleeps
  after ~5 min of inactivity then wakes automatically on the next connection
  (the first query after idle is slow). Upgrade if you need more.
- **Render free web service**: sleeps after ~15 min idle and wakes on the
  next request (cold start takes ~30-60s).
- **Media files** are stored on the container's local disk (ephemeral).
  There are currently no file/image uploads in the app, so this is fine;
  add S3 if you introduce uploads later.
- **Email** uses Django's console backend. Wire a real SMTP backend
  (e.g. SendGrid) in production settings before relying on password reset.
