import fs from "node:fs";
import path from "node:path";
import { expect, test } from "@playwright/test";

const root = path.resolve(process.cwd(), "..");
const screenshotRoot = path.join(root, "evidence", "display-qualification", "screenshots");
const viewports = { desktop: { width: 1440, height: 900 }, compact: { width: 800, height: 1000 } };

async function openRun(page, runId, viewport = viewports.desktop) {
  await page.setViewportSize(viewport);
  await page.goto(`/?run=${runId}#/browse/lifeline:mission-assurance`);
  await expect(page.locator(".lifeline-shell")).toBeVisible({ timeout: 15_000 });
  await expect(page.locator(".connection-banner")).toContainText("REPLAY COMPLETE", { timeout: 20_000 });
}

test.beforeAll(() => fs.mkdirSync(screenshotRoot, { recursive: true }));

for (const runId of ["DISPLAY-V11-T01", "DISPLAY-V11-T05", "DISPLAY-V11-T11", "DISPLAY-V11-T13", "DISPLAY-V11-T14", "DISPLAY-V11-T15"]) {
  for (const [name, viewport] of Object.entries(viewports)) {
    test(`${runId} ${name} qualification screenshot`, async ({ page }) => {
      await openRun(page, runId, viewport);
      await page.screenshot({ path: path.join(screenshotRoot, `${runId}-${name}.png`), fullPage: true });
    });
  }
}

test("OD-01 keeps mission, assurance, health, energy, evidence, and time visible", async ({ page }) => {
  await openRun(page, "DISPLAY-V11-T01");
  for (const text of ["Aircraft", "Delivery", "Timeliness", "Assurance", "Operator link", "Navigation confidence", "Evidence", "Coordinated mission timeline", "T+"]) {
    await expect(page.getByText(text, { exact: false }).first()).toBeVisible();
  }
});

test("OD-02 explains unknown and stale critical data without color", async ({ page }) => {
  await openRun(page, "DISPLAY-V11-T11", viewports.compact);
  await expect(page.getByText("UNKNOWN", { exact: true }).first()).toBeVisible();
  await expect(page.getByText(/CRITICAL DATA STALE OR INVALID/)).toBeVisible();
  await expect(page.getByText("Operator link", { exact: true })).toBeVisible();
  await expect(page.getByText("Navigation confidence", { exact: false })).toBeVisible();
});

test("OD-03 shows the T-05 decision basis and rejected RETURN", async ({ page }) => {
  await openRun(page, "DISPLAY-V11-T05");
  await expect(page.getByText("CONTROLLED_LAND", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("NAVIGATION_INVALID", { exact: true }).first()).toBeVisible();
  await expect(page.locator("dt", { hasText: "Requirements" }).locator("xpath=following-sibling::dd[1]")).toContainText("A-");
  await expect(page.locator("dt", { hasText: "Hazards" }).locator("xpath=following-sibling::dd[1]")).toContainText("H-");
  await expect(page.getByText(/RETURN/).first()).toBeVisible();
  await expect(page.getByText(/T\+20\.0/)).toBeVisible();
});

test("OD-04 failed WebSocket replaces operational content with unavailable text", async ({ page }) => {
  await page.addInitScript(() => {
    globalThis.WebSocket = class {
      constructor() { setTimeout(() => this.onerror?.(new Event("error")), 100); }
      close() {}
    };
  });
  await page.goto("/?run=DISPLAY-V11-T11#/browse/lifeline:mission-assurance");
  await expect(page.getByText(/DATA SOURCE UNAVAILABLE/)).toBeVisible({ timeout: 15_000 });
  await expect(page.locator(".lifeline-shell")).toHaveCount(0);
});

test("OD-05 reaches the recorded terminal state and labels replay complete", async ({ page }) => {
  await openRun(page, "DISPLAY-V11-T05");
  await expect(page.getByText("SAFE_STOP", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("REPLAY COMPLETE", { exact: true })).toBeVisible();
});

test("untrusted rationale and identifier are rendered as text, never HTML", async ({ page }) => {
  await page.addInitScript(() => {
    const payload = {
      run_id: '<img id="pwn" src=x onerror=alert(1)>', mission_state: "OUTBOUND", assurance_state: "WATCH",
      recommended_action: "CONTINUE", operator_link_available: true, navigation_confidence: 0.9,
      energy_margin_wh: 20, navigation_confidence_valid: true, operator_link_available_valid: true,
      energy_margin_wh_valid: true, decision_code: "TEST", decision_summary: '<script id="evil">bad()</script>',
      requirement_ids: ["REQ-TEST"], hazard_ids: [], rejected_actions: [], verification_status: "PENDING"
    };
    globalThis.WebSocket = class {
      constructor() {
        setTimeout(() => this.onopen?.(), 50);
        setTimeout(() => this.onmessage?.({ data: JSON.stringify({ message_type: "snapshot", sequence: 1, sim_time_s: 1, payload }) }), 100);
      }
      close() {}
    };
  });
  await page.goto("/?run=DISPLAY-V11-T01#/browse/lifeline:mission-assurance");
  await expect(page.getByText(/<script id="evil">bad\(\)<\/script>/)).toBeVisible({ timeout: 15_000 });
  await expect(page.locator("#evil, #pwn")).toHaveCount(0);
});

test("the dashboard exposes replay inspection but no mission-control request", async ({ page }) => {
  const requests = [];
  page.on("request", (request) => requests.push({ method: request.method(), url: request.url() }));
  await openRun(page, "DISPLAY-V11-T01");
  await expect(page.locator(".lifeline-shell form, .lifeline-shell textarea")).toHaveCount(0);
  await expect(page.locator("#lifeline-pause, #lifeline-speed, #lifeline-seek")).toHaveCount(3);
  await expect(page.getByText(/arm|launch|inject mission/i)).toHaveCount(0);
  expect(requests.filter((item) => /control|arm|launch|return|land|inject|start/i.test(new URL(item.url).pathname))).toEqual([]);
  expect(requests.every((item) => item.method === "GET")).toBeTruthy();
});

test("medical workflow shows request, manifest, map, custody, and accepted receipt", async ({ page }) => {
  await openRun(page, "DISPLAY-V11-T01");
  await expect(page.getByText("REQ-ECHO-017", { exact: true })).toBeVisible();
  await page.getByText(/Manifest ·/).click();
  await expect(page.getByText(/Sterile gauze compress/)).toBeVisible();
  await expect(page.getByText("RECEIVING_STATION", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("ACCEPTED", { exact: true }).first()).toBeVisible();
  await expect(page.locator("svg[aria-label*='local NED']")).toBeVisible();
  await expect(page.getByText("Explain this moment", { exact: true })).toBeVisible();
});

test("independent logistics outcomes remain visible after aircraft recovery", async ({ page }) => {
  await openRun(page, "DISPLAY-V11-T13");
  await expect(page.getByText("RECOVERED", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("UNCONFIRMED", { exact: true }).first()).toBeVisible();
  await openRun(page, "DISPLAY-V11-T14");
  await expect(page.getByText("REJECTED", { exact: true }).first()).toBeVisible();
  await openRun(page, "DISPLAY-V11-T15");
  await expect(page.getByText("LATE", { exact: true }).first()).toBeVisible();
});
