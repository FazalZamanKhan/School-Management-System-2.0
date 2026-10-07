# Production Browser/UI Certification (Phase 43)

Executable Playwright suite for the deployed Perfect Foundation SMS portal.
Runs against production frontend and backend. Uses real, authorized browser
sessions supplied through environment variables -- never commits credentials.

## Prerequisites

- Node 18+, `npm install` in this directory (installs `@playwright/test`).
- `npx playwright install chromium` once (browsers downloaded locally, not committed).
- One of these per role used:
  - `P43_<ROLE>_SESSIONID` env var with a valid Django `sessionid` cookie value, or
  - `P43_SESSIONS_DIR=/path/to/dir` pointing at Netscape cookie files named:
    - `sa_frostfire.txt` (SUPER_ADMIN)
    - `sa_flora.txt` (ADMIN)
    - `sa_SA-EMP-0001.txt` (TEACHER)
    - `sa_SA-ST-0001.txt` (STUDENT)
    - `sa_DI-staff.txt` (STAFF)

Credentials are NEVER stored in this repo. Sessions are read at runtime.

## Run against production

```bash
set "P43_SESSIONS_DIR=C:\secure\intended\dir"
npm run test
```

Or run against the local servers:

```bash
P43_BASE_URL=http://127.0.0.1:5173 npm test
```

Role-specific tests skip when their session variables are unavailable.

## Test files (10 role/files)

- `tests/auth.spec.js` - login page UI, validation, unauthenticated redirect, dashboard reach
- `tests/super-admin.spec.js`
- `tests/admin.spec.js`
- `tests/teacher.spec.js`
- `tests/student.spec.js`
- `tests/staff.spec.js`
- `tests/navigation.spec.js`
- `tests/authorization.spec.js`
- `tests/responsive.spec.js`
- `tests/console-network.spec.js`

## Output

- HTML report: `npx playwright show-report`
- Screenshots/traces auto-captured on failure under `test-results/`.

## Honest reporting

A verdict is produced only from actual executed tests. Tests skipped due to a
missing session are reported as SKIPPED, never as passing.
