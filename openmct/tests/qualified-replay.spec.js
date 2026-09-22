import fs from "node:fs";
import path from "node:path";
import { expect, test } from "@playwright/test";

const root = path.resolve(process.cwd(), "..");
const screenshotRoot = path.join(root, "evidence", "demo-screenshots");
const t01 = "LFL-T01-PX4-20260922T120613Z-A800";
const t05 = "LFL-T05-PX4-20260922T185205Z-CDF9";

async function openRecordedPx4(page, runId, viewport = { width: 1440, height: 900 }) {
  await page.setViewportSize(viewport);
  await page.goto("/?run=" + runId + "#/browse/lifeline:mission-assurance");
  await expect(page.locator(".lifeline-shell")).toBeVisible({ timeout: 15_000 });
  await expect(page.locator(".connection-banner")).toContainText("REPLAY COMPLETE", { timeout: 30_000 });
  await expect(page.locator(".connection-banner strong")).toHaveText("PX4 SITL · Recorded replay");
  await page.locator("#lifeline-presentation").click();
  await expect(page.locator(".l-shell__pane-tree")).toHaveClass(/l-pane--collapsed/);
  await expect(page.locator(".l-shell__pane-inspector")).toHaveClass(/l-pane--collapsed/);
}

async function seekToTime(page, runId, targetTimeS) {
  const history = await page.request.get("http://127.0.0.1:8875/api/v1/history?run_id=" + runId);
  expect(history.ok()).toBeTruthy();
  const points = await history.json();
  const index = points.reduce((best, point, candidate) =>
    Math.abs(point.sim_time_s - targetTimeS) < Math.abs(points[best].sim_time_s - targetTimeS) ? candidate : best, 0);
  await page.locator("#lifeline-seek").evaluate((element, value) => {
    element.value = String(value);
    element.dispatchEvent(new Event("input", { bubbles: true }));
  }, index);
  return points[index];
}

test.beforeAll(() => fs.mkdirSync(screenshotRoot, { recursive: true }));

test("capture qualified T-01 receiving-station handoff", async ({ page }) => {
  await openRecordedPx4(page, t01);
  const point = await seekToTime(page, t01, 79.437);
  expect(point.delivery_outcome).toBe("ACCEPTED");
  expect(point.receipt_status).toBe("ACCEPTED");
  await expect(page.locator(".outcome-strip")).toContainText("On time");
  await expect(page.locator(".request-panel")).toContainText("RECEIVING_STATION");
  await page.screenshot({ path: path.join(screenshotRoot, "px4-t01-handoff.png") });
});

test("capture qualified T-01 completed delivery and recovery", async ({ page }) => {
  await openRecordedPx4(page, t01);
  await expect(page.locator(".outcome-strip")).toContainText("Recovered");
  await expect(page.locator(".outcome-strip")).toContainText("Accepted");
  await expect(page.locator(".outcome-strip")).toContainText("On time");
  await page.screenshot({ path: path.join(screenshotRoot, "px4-t01-recovered.png") });
});

test("capture qualified T-05 contingency decision", async ({ page }) => {
  await openRecordedPx4(page, t05);
  const point = await seekToTime(page, t05, 22.082);
  expect(point.decision_code).toBe("NAVIGATION_INVALID");
  await expect(page.locator(".decision-panel")).toContainText("Controlled landing");
  await expect(page.locator(".decision-panel")).toContainText("Return");
  await expect(page.locator(".outcome-strip")).toContainText("Custody: Aircraft");
  await page.screenshot({ path: path.join(screenshotRoot, "px4-t05-decision.png") });
});

test("capture qualified T-05 observed landing without delivery", async ({ page }) => {
  await openRecordedPx4(page, t05, { width: 1366, height: 768 });
  await expect(page.locator(".outcome-strip")).toContainText("Landed and stopped");
  await expect(page.locator(".outcome-strip")).toContainText("Not Completed");
  await expect(page.locator(".outcome-strip")).toContainText("Not delivered");
  await expect(page.locator(".outcome-strip")).toContainText("Custody: Aircraft");
  await expect(page.locator(".outcome-strip")).not.toContainText("Returned");
  await page.screenshot({ path: path.join(screenshotRoot, "px4-t05-landed.png") });
});
