// Regression guard: the Campuses page must never fire the platform-only
// /api/schools/tenants/ endpoint for scoped (non-platform-admin) users.
//
// Background: CampusesPage used to call apiFetch(TENANTS_URL) unconditionally
// on mount. The backend's TenantListCreateView is protected by IsPlatformAdmin
// (superuser OR super_admin role) and correctly returns 403 for every other
// role, so any school-scoped admin/principal/academic who opened /campuses
// triggered a raw "You do not have permission to perform this action." 403 for
// the /api/schools/tenants/ request during normal, permitted use of the page.
//
// Contract locked in here: (1) the tenants call is gated behind
// modules.isPlatformAdmin, (2) scoped users seed the school dropdown from the
// current school context with NO tenants request, (3) the dependency array
// re-runs when the platform/admin or school scope changes.

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
const src = readFileSync(
  join(here, "..", "src", "pages", "CampusesPage.jsx"),
  "utf8"
);

const countOf = (needle) => src.split(needle).length - 1;

test("school context is consumed (currentSchool + modules.isPlatformAdmin)", () => {
  assert.match(
    src,
    /const \{ currentSchool, modules \} = useSchool\(\);/,
    "CampusesPage must read the school context"
  );
  assert.ok(
    src.includes(`from "../schoolContext"`),
    "useSchool must be imported from the school context"
  );
});

test("the tenants endpoint is only called inside the isPlatformAdmin branch", () => {
  const tenantsCall = src.indexOf("apiFetch(TENANTS_URL)");
  const platformGuard = src.indexOf("modules.isPlatformAdmin");

  assert.ok(platformGuard !== -1, "isPlatformAdmin gate must exist");
  assert.ok(tenantsCall !== -1, "tenants call must exist (platform branch)");
  assert.ok(
    tenantsCall > platformGuard,
    "apiFetch(TENANTS_URL) must appear AFTER the isPlatformAdmin check, never unconditionally"
  );
});

test("scoped users seed the dropdown from the current school, no tenants request", () => {
  assert.match(
    src,
    /const list = \[\{ id: currentSchool\.id, name: currentSchool\.name \}\];/,
    "scoped path must build the school list from currentSchool"
  );
  assert.match(
    src,
    /if \(currentSchool\?\.id\)/,
    "scoped path must require an active school id"
  );
});

test("the effect re-runs when platform or school scope changes", () => {
  assert.match(
    src,
    /}, \[currentSchool, modules\.isPlatformAdmin\]\);/,
    "effect dependencies must include currentSchool and modules.isPlatformAdmin"
  );
});

test("the sole tenants call is a chained request inside the platform branch", () => {
  assert.equal(
    countOf("apiFetch(TENANTS_URL)"),
    1,
    "the tenants call must appear exactly once, guarded"
  );
  assert.match(
    src,
    /apiFetch\(TENANTS_URL\)[\s\S]{0,40}\.then\(/,
    "apiFetch(TENANTS_URL) must be a chained request (never a bare statement)"
  );
});