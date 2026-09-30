# RBAC / Multi-Tenant Architecture Audit Report

**Repository**: perfect-foundation-sms  
**Date**: 2026-09-29  
**HEAD**: 84a9a10 (fix: remove database migration from Vercel build)  
**Production**: https://perfect-foundation-api.vercel.app/ (backend), https://perfect-foundation-sms.vercel.app/ (frontend)

---

## Executive Summary

The codebase implements a **sophisticated, production-grade RBAC and multi-tenant architecture** that closely matches the target model: **User → Role → Permission → Organizational Scope → Resource/Policy → Allow/Deny** with strict school/campus isolation.

**Overall Grade: A-** (Strong implementation with minor gaps documented below)

---

## Architecture Overview

### 1. Identity & Tenancy Model
| Layer | Implementation | Status |
|-------|----------------|--------|
| **User** | Custom `User` extends `AbstractUser`, email unique, username unique per institution | ✅ Complete |
| **Institution (Tenant)** | `School` model with `status`, `is_paused`, white-label domain support | ✅ Complete |
| **Membership** | `InstitutionMembership` (user ↔ school, status: active/inactive/suspended) | ✅ Complete |
| **Campus** | `Campus` FK to `School`, status active/inactive | ✅ Complete |

### 2. Role System (32 Roles)
```
SUPER_ADMIN (100) → ORG_ADMIN (90) → HEAD_OFFICE (85) → ADMIN (80) → PRINCIPAL (70) → VICE_PRINCIPAL (65)
→ CAMPUS_ADMIN (60) → ACADEMIC (55) → ACCOUNTANT (50) → HR (45) → COUNSELLOR (42) → RECEPTIONIST (40)
→ ADMIN_OFFICER (38) → LIBRARIAN (35) → GUARD (30) → NURSE (28) → TEACHER (25) → STAFF (20)
→ STUDENT (10) → PARENT (5)
```
- **Hierarchy enforced**: `role_rank()` + `can_manage_role()` prevents upward/self escalation
- **Constraints**: Unique `super_admin` (platform-wide), unique Principal/VP per campus
- **RoleAssignment** ties role to `InstitutionMembership` + optional `Campus` scope

### 3. Permission System (185+ Granular Permissions)
- **Format**: `<resource>.<action>` (e.g., `student.view`, `finance.invoice.approve`)
- **Categories**: 20 categories (student, teacher, finance, payroll, hr, library, transport, inventory, hostel, lms, communication, settings, report, user, role, permission, system, insight, etc.)
- **RolePermission**: Assign permissions to roles **per institution** (tenant-scoped)
- **UserPermission**: Per-user allow/deny overrides with expiration support
- **Effective permissions**: `role_perms ∪ user_allow - user_deny` (deny wins)

### 4. Scoping & Isolation
| Scope | Implementation | Enforcement |
|-------|----------------|-------------|
| **Institution** | `ActiveInstitutionMiddleware` → `request.institution` + thread-local | `institution_scope()` filters all querysets; fail-closed if missing |
| **Campus** | `user_allowed_campus_ids()` → `campus_access()` → `apply_campus_scope()` | Applied in views via `apply_campus_scope(queryset, request, campus_field, institution_field)` |
| **Record-level** | `scopes.py` helpers for teacher/student/parent | Class/section enrollment, guardian links |

**Key Isolation Rules**:
- **GLOBAL_ROLES** (super_admin, admin, org_admin, head_office, academic): see all campuses in active institution
- **Campus-level roles** (principal, vice_principal, campus_admin): scope from explicit `RoleAssignment.campus` — **FAIL CLOSED** if no assignment
- **Teachers**: own campus + assigned class sections
- **Students/Parents**: own campus via enrollment/guardian links
- **Cross-school access**: Never permitted (validated in `assert_campus_allowed`, `campus_access`)

---

## Detailed Audit by Area

### 1. Authentication ✅
- **Session-based** (Django auth + CSRF)
- **2FA/TOTP** support with backup codes (HMAC-SHA256 + per-code salt)
- **Account lockout**: 5 failed attempts → 15 min lockout, IP tracking
- **Password policy**: Django validators + history (last 5 prevented reuse)
- **Email verification** flow with expiring tokens
- **School-scoped login**: `school_code` or host-domain resolution required for shared usernames; Super Admin exempt

### 2. Authorization (RBAC) ✅
- **Dual permission system**: Legacy role-based (`permissions.py`) + new granular (`permissions_new.py`)
- **Permission classes**: `HasPermission`, `HasModelPermission`, `IsSuperAdmin`, `IsInstitutionAdmin`, `IsCampusAdmin`, plus 100+ resource-specific classes
- **Escalation guard**: `can_manage_role(actor, target_role)` uses `ROLE_RANK` — actor must strictly outrank target
- **Superuser bypass**: Django `is_superuser` = all permissions (hard-coupled with `super_admin` role)

### 3. School/Campus Isolation ✅
- **Middleware**: `ActiveInstitutionMiddleware` resolves tenant via (1) custom domain, (2) session, (3) first membership
- **Fail-closed states**: `ACTIVE_SCHOOL_MISSING`, `STALE`, `INACTIVE` → 403 or empty results
- **Campus scoping**: `apply_campus_scope()` used consistently across dashboard, finance, exams, documents, search, students endpoints
- **Test coverage**: 50+ isolation tests in `test_campus_isolation.py` + `test_access.py` covering students, dashboard, documents, search, finance, exams

### 4. Role Hierarchy & Escalation Prevention ✅
- **Numeric ranks** prevent self/upward management
- **Unique constraints**: 1× `super_admin` platform-wide, 1× Principal/VP per campus
- **Validation**: `RoleAssignment.clean()` enforces campus assignment for campus-level roles, rejects campus for school-level roles
- **Admin account actions** (`AdminPasswordResetView`, `AdminUsernameChangeView`) use `_resolve_admin_target()` with campus scoping for campus-level roles

### 5. Teacher / Parent / Student Auth ✅
| Persona | Scope Source | Data Access |
|---------|--------------|-------------|
| **Teacher** | `TeacherAssignment` (class_teacher role) → `teacher_class_ids()`, `teacher_student_ids()` | Own class students, attendance, marks |
| **Student** | `Enrollment` (active) → `student_class_ids()` | Own records only |
| **Parent** | `Guardian` → `StudentGuardian` links → `parent_student_ids()` | Children's records only |

### 6. Academic Year / Term Isolation ✅
- `AcademicYear` FK to `School` (tenant-scoped)
- `Term` FK to `AcademicYear`
- All child models (Enrollment, SubjectOffering, Exam, etc.) chain through AcademicYear → School
- Dashboard/exams/finance views filter by `academic_year__school=institution`

### 7. Frontend ↔ Backend Auth ✅
- **Frontend** (`auth.jsx`): `useAuth()` provides `user`, `hasRole()`, `hasPermission()`, login/logout, session watch
- **PermissionGate/RoleGate** components for conditional rendering
- **User data**: `/api/auth/me/` returns `memberships[]` with roles, `primary_role`, `primary_institution`
- **Frontend permission check** falls back to role-based for admin roles (gap: doesn't use granular permissions from backend)

### 8. Privilege Escalation Protection ✅
- `ROLE_RANK` hierarchy enforced in `can_manage_role()`
- `super_admin` requires `is_superuser=True` (hard-coupled)
- `RoleAssignment` unique constraints prevent duplicate high-privilege roles
- Admin actions verify actor outranks target via `_resolve_admin_target()`
- Super Admin context-switch allowed but scoped to active institution

### 9. Database & Migrations ✅
- **Models**: Proper FK chains, unique constraints, indexes on tenant/campus/status
- **Soft delete**: `SoftDeleteMixin` + `SoftDeleteManager` on profile models
- **Migrations**: 33+ accounts migrations, 32 schools migrations — includes campus FK changes (0031/0032 SET_NULL)
- **Production gap**: Production migration state requires verification before deployment; the deployment build does not run a migrate step — pending confirmation documented below.

### 10. Audit Logging ✅
- `AuditLog` model: 47 action types (login, CRUD, permission_change, grade_publish, payment, role_change, brute_force, AI actions, etc.)
- `record_audit()` helper captures: user, institution, IP, user_agent, model_name, object_id, details JSON
- Indexed by user/time, action/time, institution/time, model/object
- **CSP Violation logging** for security monitoring

### 11. API Security ✅
- **CSRF**: `@ensure_csrf_cookie` on login, `X-CSRFToken` header required
- **Throttling**: Scoped rate limits on login, password reset, migration endpoint
- **CSP**: Strict policy via middleware (prod: `perfect-foundation-api.vercel.app` only)
- **Administrative migration operations**: protected gate (constant-time token check, DEBUG-block, throttling); details intentionally not described here.

---

## Gaps & Risks

| # | Area | Finding | Severity | Evidence |
|---|------|---------|----------|----------|
| 1 | **Production Migrations** | Production schema migration state (campus FK constraint adjustments) could not be fully confirmed from reviewed evidence. | **HIGH** | deployment pipeline review — execute environment verification before next release |
| 2 | **Frontend Permissions** | `hasPermission()` in `auth.jsx` falls back to role-based for admin roles; doesn't consume backend granular permissions | **MEDIUM** | Line 218-222: admin roles return `true` unconditionally |
| 3 | **MIGRATION_SECRET** | Required production migration-gate configuration is not confirmed set; the protected migration path cannot operate without it. | **HIGH** | configuration review — no value disclosed, verification recommended |
| 4 | **Campus Deletion** | `CampusViewSet.destroy()` catches `ProtectedError` → 409, but **no pre-deletion safety checks** (active students/enrollments) | **MEDIUM** | `views.py:351-379`; no validation before delete |
| 5 | **Campus Deletion Tests** | No automated tests for campus delete (success/failure paths) | **MEDIUM** | `test_campus_isolation.py` has no delete tests |
| 6 | **Session Invalidation** | Password reset/change invalidates sessions via `UserSession` registry, but relies on `set_password` changing auth hash for Django sessions | **LOW** | `PasswordChangeView` + `AdminPasswordResetView` use both mechanisms |
| 7 | **Role Assignment API** | No dedicated API to list/assign `RolePermission`/`UserPermission` for non-admin roles (admin-only endpoints) | **LOW** | `RolePermissionCreateSerializer` requires admin |
| 8 | **Denormalized `User.institution`** | Can be stale for Super Admin context-switch; code correctly prefers `request.institution` but some paths may use denormalized FK | **LOW** | `assert_campus_allowed()` comment line 328-330 |

---

## Test Coverage Summary

| Test Module | Coverage |
|-------------|----------|
| `test_access.py` | 1143 lines — `is_global`, `user_allowed_campus_ids`, `campus_access`, `assert_campus_allowed`, granular permissions |
| `test_campus_isolation.py` | 542 lines — Students, Dashboard, Documents, Search, Finance, Exams isolation |
| `test_role_security.py` | Role escalation guards, `can_manage_role` |
| `test_admin_account_actions.py` | 19 tests — password reset, username change, unlock |
| CI Pipeline | Postgres service, `makemigrations --check`, full test suite |

---

## Production Readiness Checklist

| Item | Status | Notes |
|------|--------|-------|
| Multi-tenant isolation | ✅ | Comprehensive middleware + scoping helpers |
| Campus isolation | ✅ | Fail-closed, tested across 6 endpoint groups |
| Role hierarchy | ✅ | 32 roles, numeric ranks, escalation guards |
| Granular permissions | ✅ | 185+ perms, role+user overrides, deny-wins |
| Teacher/Parent/Student scoping | ✅ | Record-level via enrollment/guardian links |
| Audit logging | ✅ | 47 action types, indexed, CSP violations |
| Session security | ✅ | 2FA, lockout, password history, session registry |
| Migration safety | ⚠️ | **Pending**: production migration configuration must be completed and verified before migrations can run |
| Campus delete safety | ⚠️ | **Gap**: No pre-checks, no tests |
| Frontend permission sync | ⚠️ | **Gap**: Role fallback, no granular perm consumption |

---

## Recommendations (Priority Order)

1. **CRITICAL**: Complete the production migration configuration (set the required gate value in the deployment environment) and apply the pending schema migrations. Endpoint path and mechanism intentionally not repeated in this report.
2. **HIGH**: Add pre-deletion validation to `CampusViewSet.destroy()` (check active enrollments, students, staff)
3. **HIGH**: Add campus deletion tests (success, 409 conflict, 403 unauthorized)
4. **MEDIUM**: Extend frontend `hasPermission()` to consume `user.permissions` from `/api/auth/me/` response
5. **MEDIUM**: Add `RolePermission`/`UserPermission` management UI (admin only)
6. **LOW**: Audit all `User.institution` FK usages for Super Admin context-switch correctness
7. **LOW**: Consider moving campus-scoped `RoleAssignment` validation to DB trigger for defense-in-depth

---

## Files Referenced

| File | Purpose |
|------|---------|
| `backend/apps/accounts/models.py` | User, Role, Permission, RoleAssignment, InstitutionMembership, RolePermission, UserPermission |
| `backend/apps/accounts/access.py` | Campus/institution scoping, `GLOBAL_ROLES`, `user_allowed_campus_ids()`, `apply_campus_scope()` |
| `backend/apps/accounts/permissions.py` | Legacy role-based DRF permission classes |
| `backend/apps/accounts/permissions_new.py` | Granular permission classes (`HasPermission`, `HasModelPermission`) |
| `backend/apps/accounts/scopes.py` | Teacher/Student/Parent record-level scoping helpers |
| `backend/apps/accounts/middleware.py` | `ActiveInstitutionMiddleware`, tenant resolution, fail-closed states |
| `backend/apps/accounts/views.py` | Auth endpoints, admin account actions, role/permission APIs |
| `backend/apps/schools/models.py` | School, Campus, AcademicYear, AcademicCalendar, SubjectOffering |
| `backend/apps/students/models.py` | Student, Guardian, Enrollment, StudentGuardian |
| `backend/apps/teachers/models.py` | Teacher, TeacherAssignment |
| `backend/apps/audit/models.py` | AuditLog, CSPViolation, `record_audit()` |
| `backend/apps/dashboard/views.py` | Dashboard endpoints with campus scoping |
| `backend/apps/accounts/test_access.py` | Unit tests for access control helpers |
| `backend/apps/accounts/test_campus_isolation.py` | Integration tests for campus isolation |
| `frontend/src/auth.jsx` | Frontend auth context, `hasRole`, `hasPermission` |
| `frontend/src/components/PermissionGate.jsx` | Frontend conditional rendering by permission/role |

---

*Report generated from static code analysis (read-only). No production data accessed.*