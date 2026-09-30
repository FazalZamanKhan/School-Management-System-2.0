# PHASE 168 REPORT — ADMIN MANAGEMENT FINAL VERIFICATION

## RESULT: `VERIFIED — LOCAL/TEST ONLY`

- Production database access: **BLOCKED — NO APPROVED READ-ONLY PRODUCTION ACCESS PATH** (never attempted; all verification conducted against the local test database only).
- All admin-management code, migrations, and tests verified locally.
- Frontend build **NOT VERIFIED** (PowerShell execution policy blocks `npm`; no bypass attempted).

---

## 1. SCOPE

Final repository-local verification of the **School Admin / Campus Admin / Principal / Vice Principal** management feature:

- Backend endpoints: `SchoolViewSet.admins/assign_admin/remove_admin`, `CampusViewSet.admin/assign_admin/remove_admin` (`backend/apps/schools/views.py`)
- DB constraints on `accounts_roleassignment` (incl. migration `0034`)
- Fail-closed campus authorization (`backend/apps/accounts/access.py`)
- Frontend admin sections (`TenantsPage.jsx`, `CampusesPage.jsx`)
- Test reconciliation (`backend/apps/accounts/test_access.py`)

---

## 2. GATE 1 — TEST DATABASE IDENTITY

| Check | Result |
|---|---|
| Test DB engine | SQLite in-memory `:memory:` (`config.settings.test`) |
| Verified via | `python manage.py test` runbook identity check |
| Production DB touched | **NO** |

Status: **PASS**

## 3. GATE 2 — APPROVED CORRECTIONS ONLY

| Correction | Type |
|---|---|
| `migrations/0034_roleassignment_unique_campus_admin_per_campus.py` | New constraint migration (corrective) |
| `test_access.py` — explicit `RoleAssignment.campus` rows for campus-level role fixtures | Test reconciliation only; authorization implementation NOT weakened |
| `models.py` — added `unique_campus_admin_per_campus` UniqueConstraint | Implements singleton Campus Admin contract correctly |

Non-modifications confirmed: no codepath changes to `access.py` fail-closed logic; no weakening of conductor ID / collection access protections.

Status: **PASS**

## 4. GATE 3 — VERIFICATION (DB CONSTRAINTS)

Constraint evidence via `check_indexes.py` on `accounts_roleassignment` (all present on test schema):

| Constraint | Condition | Status |
|---|---|---|
| `unique_super_admin_role` | role='super_admin' | VERIFIED |
| `unique_role_per_membership` | campus IS NULL | VERIFIED |
| `unique_role_per_membership_campus` | campus IS NOT NULL | VERIFIED |
| `unique_campus_admin_per_campus` | role='campus_admin' AND campus IS NOT NULL | **VERIFIED (migration 0034)** |
| `unique_principal_per_campus` | role='principal' | VERIFIED |
| `unique_vice_principal_per_campus` | role='vice_principal' | VERIFIED |

## 5. GATE 3 — TEST RESULTS

```
python -m pytest apps/schools/tests.py apps/accounts/test_school_provisioning.py \
  apps/accounts/test_campus_isolation.py apps/accounts/test_access.py
= 124 passed, 1 warning, 21 subtests passed in 110.67s
```

### Reconciliation of `apps/accounts/test_access.py`

- 9 previously-failing tests corrected by adding explicit `RoleAssignment.campus` rows for campus-level roles (CAMPUS_ADMIN, PRINCIPAL, VICE_PRINCIPAL fixtures).
- Corrected per the authoritative fail-closed contract: `RoleAssignment.campus` is the ONLY authorization source for campus-level roles; `StaffProfile.primary_campus` is NOT used as fallback. Authorization logic untouched.

### Singleton enforcement test (migration 0034)

- A focused concurrent-duplicate Campus Admin test confirms the DB-level partial unique index rejects a second `CAMPUS_ADMIN` for the same campus (passes).

## 6. GATE 3 — PRE-EXISTING FAILURES (NOT REGRESSIONS)

`python -m pytest apps/accounts/test_regressions.py` — targeted report:

- **23 failed, 13 passed, 1 subtest passed.**
- All 23 failures are in `DesignationRoleMappingRegressionTests` (Phase 84 staff-designation → role mapping feature). Symptom: `staff.user` is `None` after `StaffProfileSerializer.create()` with `create_account=True`.

**Pre-existing proof:** Repeated run with ALL admin-management changes stashed (`git stash push` of `models.py`, `views.py`, `test_access.py`): identical 23 failures with no stash difference. Root causes trace to the Phase 84 serializer/designation path, NOT to this feature.

**Context on earlier `TransactionManagementError`:** An earlier combined run surfaced a `TransactionManagementError`/`validate_no_broken_transaction`. This is a residual effect of the same pre-existing broken Phase 84 tests (IntegrityError raised inside the designation serializer path while a test transaction is open). The full reconfirmed run of the 5 core files + `test_regressions.py` completes cleanly:

```
python -m pytest apps/schools/tests.py apps/accounts/test_school_provisioning.py \
  apps/accounts/test_campus_isolation.py apps/accounts/test_access.py \
  apps/accounts/test_regressions.py
= 137 passed, 23 failed (all 23 = pre-existing Phase 84 designation tests)
```

## 7. MIGRATION EVIDENCE

| Check | Result |
|---|---|
| `python manage.py showmigrations accounts` | All applied through `0034_roleassignment_unique_campus_admin_per_campus` |
| `python manage.py makemigrations --check --dry-run` | No changes detected |
| `python manage.py sqlmigrate accounts 0034` | Partial unique index SQL correct |
| Migration SQL | `CREATE UNIQUE INDEX "unique_campus_admin_per_campus" ON "accounts_roleassignment" ("campus_id", "role") WHERE ("campus_id" IS NOT NULL AND "role" = 'campus_admin')` |

## 8. ENVIRONMENT

- Windows + PowerShell 5.1, Python 3.14.7, Django 6.1, pytest 9.1.1, pytest-django 4.14.0, SQLite 3.50.4
- Frontend build: NOT VERIFIED (PowerShell policy blocks `npm`; no bypass)

## 9. CONCLUSION

- Admin Management implementation: **VERIFIED — LOCAL/TEST ONLY**
- 124/124 core admin-management tests pass; constraints enforced at DB level; migrations clean.
- 23 `test_regressions.py` failures are **pre-existing** (reproduced identically without this feature's changes) and belong to the phase-84 designation mapping workstream.
- No production-side verification is possible under the standing credential policy.