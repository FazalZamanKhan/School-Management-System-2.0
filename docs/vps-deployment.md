# VPS Deployment Guide (Gunicorn + Nginx)

> This alternative guide assumes the older separate frontend Vercel project.
> For the current one-project deployment, use [Vercel Services](VERCEL_SERVICES.md).

Alternative to Render: run the Django backend on a Linux server the client
owns, using **Gunicorn** behind **nginx** with HTTPS. The frontend stays on
Vercel and the database stays on Neon.

Architecture after this guide:

```
Browser ──> https://perfect-foundation-sms.vercel.app  (Vercel frontend)
                │  /api/*  rewritten by frontend/vercel.json
                ▼
           https://api.example.com/api/*  (this VPS, nginx → gunicorn → Django)
                │
                ▼
           Neon Postgres  (via DATABASE_URL in backend/.env)
```

> Because Vercel proxies `/api/*` to the VPS **server-side**, the browser only
> ever talks to `*.vercel.app`. Cookies stay same-site and the existing
> session/CSRF flow works unchanged. The VPS does not need to be on the
> client's DNS to be reached from the browser — it only needs to be reachable
> by Vercel's servers. But it still needs a public hostname + HTTPS for TLS.

## Prerequisites

- Ubuntu 24.04 server (needed for Python 3.12; Django 6.1 requires it)
- A DNS record pointing `api.example.com` (or any subdomain) at the server IP
- Root or sudo access
- The Neon connection string (from the Neon console)

## 1. System packages

```sh
sudo apt update
sudo apt install -y python3 python3-venv python3-pip nginx git certbot python3-certbot-nginx
```

## 2. App user and directory

```sh
sudo useradd -r -m -d /opt/perfect-foundation -s /usr/sbin/nologin perfect
sudo -u perfect mkdir -p /opt/perfect-foundation/backend
```

## 3. Get the code (as the `perfect` user)

The repo is public, so a plain clone works:

```sh
sudo -u perfect git clone --branch master --single-branch \
  https://github.com/lordvalicious/perfect-foundation-sms.git \
  /opt/perfect-foundation/backend-src
```

**Important:** clone into a temp dir, then move the `backend/` folder into
place — the deploy files live in the repo but `.env` must be a sibling of
`manage.py`:

```sh
sudo mv /opt/perfect-foundation/backend-src/backend /opt/perfect-foundation/
sudo rm -rf /opt/perfect-foundation/backend-src
sudo chown -R perfect:perfect /opt/perfect-foundation
```

## 4. Python virtualenv + dependencies

```sh
cd /opt/perfect-foundation/backend
sudo -u perfect python3 -m venv .venv
sudo -u perfect .venv/bin/pip install -r requirements.txt gunicorn
```

## 5. Environment file

```sh
sudo -u perfect cp .env.production.example .env
sudo -u perfect nano .env
```

Fill in:

| Variable | Value |
| --- | --- |
| `DJANGO_SECRET_KEY` | `python -c "import secrets; print(secrets.token_urlsafe(50))"` |
| `DJANGO_ALLOWED_HOSTS` | `api.example.com` (your backend hostname) |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | the exact Vercel URL, e.g. `https://perfect-foundation-sms.vercel.app` |
| `DATABASE_URL` | your Neon connection string (keeps `?sslmode=require`) |

## 6. Migrate, static files, admin user

```sh
cd /opt/perfect-foundation/backend
sudo -u perfect .venv/bin/python manage.py migrate --noinput
sudo -u perfect .venv/bin/python manage.py collectstatic --noinput
sudo -u perfect .venv/bin/python manage.py createsuperuser
```

## 7. systemd service (gunicorn)

```sh
sudo cp backend/deploy/perfect-foundation.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now perfect-foundation
sudo systemctl status perfect-foundation     # should show active (running)
curl -s http://127.0.0.1:8000/api/health/   # -> {"status": "ok"}
```

## 8. nginx + HTTPS (certbot)

```sh
sudo cp backend/deploy/nginx-backend.conf /etc/nginx/sites-available/perfect-foundation
sudo ln -s /etc/nginx/sites-available/perfect-foundation /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx

# Issue a free Let's Encrypt cert (fills in the ssl_certificate lines):
sudo certbot --nginx -d api.example.com
```

## 9. Verify the public endpoint

```sh
curl -s https://api.example.com/api/health/   # -> {"status": "ok"}
```

## 10. Wire the frontend

Tell the developer the backend URL (e.g. `https://api.example.com`). They will:

1. Set the `/api` rewrite destination in `frontend/vercel.json` to
   `https://api.example.com/api/:path*` and redeploy on Vercel.
2. Make sure `DJANGO_CSRF_TRUSTED_ORIGINS` in `backend/.env` matches the real
   Vercel URL.

## Update / redeploy after code changes

```sh
cd /opt/perfect-foundation/backend
sudo -u perfect git pull
sudo -u perfect .venv/bin/pip install -r requirements.txt
sudo -u perfect .venv/bin/python manage.py migrate --noinput
sudo -u perfect .venv/bin/python manage.py collectstatic --noinput
sudo systemctl restart perfect-foundation
```

## Notes / limitations

- **Storage:** static files live in `backend/staticfiles` (WhiteNoise serves
  them); media files are not used yet. If uploads are added later, mount a
  persistent disk and point `DJANGO_MEDIA_ROOT` at it, then serve `/media/`
  from nginx.
- **Email:** defaults to console output. Set the `DJANGO_EMAIL_*` variables in
  `.env` for real SMTP (password reset, notifications).
- **Backups:** `pg_dump` the Neon database regularly:
  `pg_dump "$DATABASE_URL" > backup.sql`.
