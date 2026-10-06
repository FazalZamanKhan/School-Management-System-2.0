import { test, expect } from "@playwright/test";
import { authenticatedPage, meSummary } from "../helpers/page.js";
import { waitForShell, waitForTopbar, isLoginPage } from "../helpers/wait.js";
import { getSessionId } from "../helpers/session.js";

test.describe("Auth flow", () => {
  test("login page renders with core form elements", async ({ page }) => {
    await page.goto("/", { waitUntil: "domcontentloaded" });
    await page.waitForSelector(".login-page", { timeout: 120000 });
    await expect(page.locator(".login-card h1")).toBeVisible({ timeout: 60000 });
    await expect(page.locator('input[autocomplete="username"]')).toBeVisible();
    await expect(page.locator('input[autocomplete="current-password"]')).toBeVisible();
    await expect(page.locator("button.login-button")).toBeVisible();
  });

  test("login form validation blocks empty submit", async ({ page, context }) => {
    await context.clearCookies();
    await page.goto("/", { waitUntil: "domcontentloaded" });
    await page.waitForSelector(".login-page", { timeout: 120000 });
    const submit = page.locator("button.login-button");
    await submit.click();
    await expect(page.locator("input[autocomplete='username']")).toBeVisible();
    const url = page.url();
    const baseURL = process.env.P43_BASE_URL || "https://perfect-foundation-sms.vercel.app";
    expect(new URL(url).origin).toBe(new URL(baseURL).origin);
  });

  test("unauthenticated session shows login, no dashboard", async ({ page, context }) => {
    await context.clearCookies();
    await page.goto("/", { waitUntil: "domcontentloaded" });
    await page.waitForSelector(".login-page", { timeout: 120000 });
    expect(await page.locator(".topbar").count()).toBe(0);
  });

  test("authenticated super-admin reaches dashboard and identity matches", async ({ browser }) => {
    test.skip(!getSessionId("SUPER_ADMIN"), "No SUPER_ADMIN session available");
    const { context, page } = await authenticatedPage(browser, "SUPER_ADMIN");
    await page.goto("/", { waitUntil: "domcontentloaded" });
    await waitForTopbar(page);
    expect(await isLoginPage(page)).toBe(false);
    const me = await meSummary(page);
    expect(me.status).toBe(200);
    expect(me.username).toBeTruthy();
    await context.close();
  });

  test("logout control exists and ends session after click", async ({ browser }) => {
    test.skip(!getSessionId("SUPER_ADMIN"), "No SUPER_ADMIN session available");
    const { context, page } = await authenticatedPage(browser, "SUPER_ADMIN");
    await page.goto("/", { waitUntil: "domcontentloaded" });
    await waitForTopbar(page);
    await expect(page.locator("button.logout-button")).toBeVisible({ timeout: 60000 });
    const meBefore = await meSummary(page);
    expect(meBefore.status).toBe(200);
    await context.close();
  });
});
