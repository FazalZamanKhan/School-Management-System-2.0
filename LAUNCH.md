# Launch Guide — From Zero to First Live School

> This guide describes the older two-project deployment. For the current
> one-project Vercel Services configuration, use [Vercel Services](docs/VERCEL_SERVICES.md).

Exact clicks, URLs and commands. Do Phase 1 once, Phase 2 per school,
Phase 3 forever.

---

## PHASE 0 — Where things live

| Thing | Where |
|---|---|
| Frontend (teachers/admins/parents) | https://perfect-foundation-sms.vercel.app |
| Backend API | https://perfect-foundation-api.vercel.app |
| Vercel projects | https://vercel.com/dashboard → team `lordvalicious-projects` |
| Public admission form | https://perfect-foundation-sms.vercel.app/apply |
| Django admin | https://perfect-foundation-api.vercel.app/admin/ |

---

## PHASE 1 — Credentials (one-time, ~30 minutes)

**Where, exactly:**

1. **vercel.com** → log in → Dashboard.
2. Click the **`perfect-foundation-api`** project card.
3. Project top tabs → **Settings** → left sidebar → **Environment Variables**.
4. For EACH variable below: paste Key + Value → tick **Production**
   → **Save**.
5. After the LAST one: **Deployments** tab → latest → **⋯ → Redeploy**.
   Variables are NOT live until this redeploy.

**Generate secrets locally:**

```
python -c "import secrets; print(secrets.token_urlsafe(50))"   # DJANGO_SECRET_KEY
python -c "import secrets; print(secrets.token_urlsafe(32))"   # CRON_SECRET
python -c "import secrets; print(secrets.token_urlsafe(24))"   # device keys
```

### 1.1 Required basics

| Variable | Value |
|---|---|
| `DJANGO_SECRET_KEY` | Generate: `python -c "import secrets; print(secrets.token_urlsafe(50))"` |
| `DJANGO_ALLOWED_HOSTS` | `perfect-foundation-api.vercel.app` (+ any custom domain) |

### 1.2 Scheduled jobs (4 crons are already coded)

| Variable | How to get it |
|---|---|
| `CRON_SECRET` | `python -c "import secrets; print(secrets.token_urlsafe(32))"` |

> Vercel Cron automatically sends `Authorization: Bearer $CRON_SECRET`.
> **Plan note:** weekday schedules (`1-6`) require Vercel Pro. On Hobby,
> either simplify schedules to daily (`0 8 * * *`), or skip Vercel crons
> and use a free external scheduler (cron-job.org) hitting the same
> four URLs with header `Authorization: Bearer <your-secret>`.

### 1.3 Email (unlocks Email tab + weekly digest + email reminders)

Pick ONE provider:

- **Brevo (free 300 emails/day):** brevo.com → SMTP & API → copy
  - `DJANGO_EMAIL_HOST=smtp-relay.brevo.com`, `DJANGO_EMAIL_PORT=587`,
    `DJANGO_EMAIL_USER=<login>`, `DJANGO_EMAIL_PASSWORD=<smtp key>`,
    `DJANGO_EMAIL_USE_TLS=1`
- **Gmail:** enable 2FA → myaccount.google.com/apppasswords → generate
  - Host `smtp.gmail.com`, port 587, user = your Gmail, password =
    the 16-char app password

Also set `DEFAULT_FROM_EMAIL=no-reply@yourdomain.edu`.

### 1.4 SMS (unlocks absence alerts + fee reminder texts)

console.twilio.com → copy **Account SID** + **Auth Token** →
Messaging → Try/Buy a number:

```
TWILIO_ACCOUNT_SID=ACxxxxxxxx
TWILIO_AUTH_TOKEN=xxxxxxxx
TWILIO_PHONE_NUMBER=+1xxxxxxxxxx
```

### 1.5 Payment gateways (each needs a merchant account)

| Gateway | Sign up | Variables |
|---|---|---|
| Stripe (cards) | dashboard.stripe.com → API keys | `STRIPE_SECRET_KEY=sk_live_…`; add webhook `https://<api>/api/finance/stripe/webhook/` for `checkout.session.completed` |
| JazzCash | payments.jazzcash.com.pk merchant registration | `JAZZCASH_MERCHANT_ID`, `JAZZCASH_PASSWORD`, `JAZZCASH_INTEGRITY_SALT`, `JAZZCASH_ENV=sandbox` first, then `live` |
| EasyPaisa | Easypay merchant onboarding (Telenor Microfinance) | `EASYPAISA_STORE_ID`, `EASYPAISA_STORE_KEY`, `EASYPAISA_ENV=sandbox` then `live` |

Until these exist the buttons simply stay hidden/disabled — safe.

### 1.6 Google Sign-In

console.cloud.google.com →

1. New project → **APIs & Services → OAuth consent screen**
   (External, add app name) → Create
2. **Credentials → Create Credentials → OAuth client ID → Web application**
3. Authorized JavaScript origins:
   `https://perfect-foundation-sms.vercel.app`
4. Copy the Client ID →

```
GOOGLE_CLIENT_ID=xxxxx.apps.googleusercontent.com
```

Only pre-created accounts can sign in (matched by email).

### 1.7 Hardware keys (when you buy devices)

Invent two strong random strings yourself, e.g.
`python -c "import secrets; print(secrets.token_urlsafe(24))"`:

```
ATTENDANCE_DEVICE_KEYS=give-to-vendor-1,give-to-vendor-2
GPS_DEVICE_KEYS=tracker-key-1
```

Give the matching string to the biometric/GPS vendor to put in their
device's webhook config. Endpoints & payload docs: `ONBOARDING.md` §2.8.

---

## PHASE 2 — Onboard the first school (~half a day)

Full detail in `ONBOARDING.md`. The short version, in order:

1. **Log in** as your admin at the frontend URL.
2. **Campuses page** → create the school's campuses
   (or Django admin for the School record itself).
3. **Settings page**, top to bottom: Academic Year (mark *active*) →
   Terms → Units → Classes → Sections → Subjects → Subject Offerings.
4. **People → Data Import**: download Students + Teachers templates,
   fill from the admission register, Validate → fix rows → Import.
   Guardians/enrollments come in automatically with students.
5. **Teachers/Staff pages**: confirm profiles; assign roles & campuses
   so each person sees only their campus.
6. **Finance**: Fee Categories → Fee Structures (per campus+class) →
   Bulk Finance → generate everyone's invoices in one click.
7. **Test money end-to-end**: record one cash payment → open the
   receipt PDF → send one fee-reminder dry-run
   (Settings → Parent Notifications).
8. **Optional modules** (each has its own page, no extra setup):
   Transport → Library → Hostel → Discipline → Health Records → LMS.
9. **Share the links**: staff get the main URL; parents get
   `/apply` for admissions and `/parent-portal` after accounts exist.
10. Flip any remaining gateway vars to `live` once merchants approve.

---

## PHASE 3 — Operating rhythm

| Cadence | Action | Where |
|---|---|---|
| Every morning (auto) | Absence alerts sent to guardians of today's absentees | automatic |
| Mon–Sat (auto) | Fee reminder cycle | automatic |
| Mondays (auto) | Weekly summary emailed to all admins | automatic |
| Weekly | Open **Reports → At-Risk**: call the High list families, chase Medium fees | Reports |
| Monthly | Data Export → Full JSON backup → store offsite | Data Export |
| Term start | New Academic Year → promote students → new fee structures | Settings / Students |

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| Cron returns 401 | Header must be exactly `Authorization: Bearer $CRON_SECRET` |
| Email tab says not configured | `DJANGO_EMAIL_HOST` missing — recheck spelling of every `DJANGO_EMAIL_*` var |
| Gateway buttons absent | Credentials missing/typo'd — endpoints return 503 by design until valid |
| Everything empty after login | User lacks an active membership for that school — fix role assignment |
| Google button absent | `GOOGLE_CLIENT_ID` unset or wrong origin (must equal frontend URL exactly) |
