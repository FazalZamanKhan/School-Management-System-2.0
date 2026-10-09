import { test, expect } from "@playwright/test";

async function openEvents(page) {
  const user = {
    id: 1, username: "event-qa-admin", is_superuser: true,
    is_staff: true, primary_role: "super_admin", email_verified: true,
    memberships: [{ institution: 1, institution_name: "QA School", status: "active", roles: [{ role: "super_admin" }] }],
  };
  const event = {
    id: 42, title: "Existing event", description: "Retained event",
    start_datetime: "2026-12-10T09:00:00Z", end_datetime: "2026-12-10T15:00:00Z",
    status: "published", audiences: [], rsvp_count: 0,
  };
  await page.route("**/api/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path === "/api/events/" && route.request().method() === "POST") {
      return route.fulfill({ status: 400, json: { title: ["Server refused this input."] } });
    }
    const payloads = {
      "/api/auth/me/": user,
      "/api/auth/active-institution/": { institution: { id: 1, name: "QA School", status: "active" }, roles: ["super_admin"] },
      "/api/schools/modules/current/": { enabled: ["events"], is_platform_admin: true, school_status: "active" },
      "/api/auth/active-campus/": { campus: null, campuses: [] },
      "/api/auth/super-admin/schools/": [],
      "/api/schools/branding/": { school_name: "QA School", theme_color: "#123456" },
      "/api/events/": [event],
    };
    return route.fulfill({ status: 200, json: payloads[path] ?? {} });
  });
  await page.goto("/events");
  await expect(page.locator(".event-card")).toHaveCount(1);
  await page.getByRole("button", { name: /Add Event/ }).click();
  return page.locator(".teacher-modal");
}

test("invalid event times preserve list and Cancel clears form error", async ({ page }) => {
  const modal = await openEvents(page);
  await modal.locator('input[name="title"]').fill("Invalid range");
  await modal.locator('input[name="start_datetime"]').fill("2026-12-10T15:00");
  await modal.locator('input[name="end_datetime"]').fill("2026-12-10T09:00");
  await modal.getByRole("button", { name: "Create Event", exact: true }).click();
  await expect(modal.getByRole("alert")).toContainText("later than the start time");
  await expect(page.locator(".event-card")).toHaveCount(1);
  await modal.getByRole("button", { name: "Cancel", exact: true }).click();
  await expect(page.locator(".teacher-modal")).toHaveCount(0);
  await expect(page.locator(".event-card")).toHaveCount(1);
  await expect(page.locator(".state-card.error")).toHaveCount(0);
  await page.getByRole("button", { name: /Add Event/ }).click();
  await expect(page.locator(".teacher-modal .state-card.error")).toHaveCount(0);
});

test("server validation failure stays in modal and does not hide existing list", async ({ page }) => {
  const modal = await openEvents(page);
  await modal.locator('input[name="title"]').fill("Server rejected");
  await modal.locator('input[name="start_datetime"]').fill("2026-12-10T09:00");
  await modal.locator('input[name="end_datetime"]').fill("2026-12-10T15:00");
  await modal.getByRole("button", { name: "Create Event", exact: true }).click();
  await expect(modal.getByRole("alert")).toContainText("Server refused this input");
  await expect(page.locator(".event-card")).toHaveCount(1);
  await expect(page.locator(".state-card.error")).toHaveCount(1);
});
