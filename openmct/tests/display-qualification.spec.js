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

for (const runId of ["DISPLAY-V11-T01", "DISPLAY-V11B-T05", "DISPLAY-V11-T11", "DISPLAY-V11-T13", "DISPLAY-V11-T14", "DISPLAY-V11-T15"]) {
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
  await expect(page.getByText("Unknown", { exact: true }).first()).toBeVisible();
  await expect(page.getByText(/CRITICAL DATA STALE OR INVALID/)).toBeVisible();
  await expect(page.getByText("Operator link", { exact: true })).toBeVisible();
  await expect(page.getByText("Navigation confidence", { exact: false })).toBeVisible();
});

test("OD-03 shows the T-05 decision basis and rejected RETURN", async ({ page }) => {
  await openRun(page, "DISPLAY-V11B-T05");
  await expect(page.getByText("Controlled landing", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("NAVIGATION_INVALID", { exact: true }).first()).toBeVisible();
  await expect(page.locator("dt", { hasText: "Requirements" }).locator("xpath=following-sibling::dd[1]")).toContainText("A-");
  await expect(page.locator("dt", { hasText: "Hazards" }).locator("xpath=following-sibling::dd[1]")).toContainText("H-");
  await expect(page.getByText(/Return/).first()).toBeVisible();
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
  await openRun(page, "DISPLAY-V11B-T05");
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

test("compact dashboard has no horizontal content clipping", async ({ page }) => {
  await openRun(page, "DISPLAY-V11-T01", viewports.compact);
  const overflow = await page.locator(".lifeline-shell").evaluate((shell) =>
    [...shell.querySelectorAll("*")]
      .filter((element) => element.scrollWidth > element.clientWidth + 2)
      .map((element) => ({
        tag: element.tagName,
        className: String(element.className),
        scrollWidth: element.scrollWidth,
        clientWidth: element.clientWidth
      }))
  );
  expect(overflow).toEqual([]);
});

test("replay seeking and Explain this moment do not leak later receipt or terminal outcomes", async ({ page }) => {
  await openRun(page, "DISPLAY-V11-T01");
  const seek = page.locator("#lifeline-seek");
  await seek.evaluate((element) => {
    element.value = "0";
    element.dispatchEvent(new Event("input", { bubbles: true }));
  });
  await expect(page.locator(".mission-meta b")).toContainText("T+0.0");
  await expect(page.locator(".outcome-strip")).toContainText("Pending");
  await expect(page.locator(".outcome-strip")).not.toContainText("Accepted");
  await expect(page.locator(".outcome-strip")).not.toContainText("Receiving Station");
  await expect(page.locator(".explain-panel")).toContainText("Delivery PENDING");
  await expect(page.locator(".explain-panel")).not.toContainText("receipt ACCEPTED");
  await expect(page.locator(".timeline-panel")).not.toContainText("RECOVERED");
  await expect(page.locator("#lifeline-run-selector")).not.toContainText("ACCEPTED");
  await expect(page.locator("#lifeline-run-selector")).not.toContainText("NOT_COMPLETED");
});

test("independent logistics outcomes remain visible after aircraft recovery", async ({ page }) => {
  await openRun(page, "DISPLAY-V11-T13");
  await expect(page.getByText("RECOVERED", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("Unconfirmed", { exact: true }).first()).toBeVisible();
  await openRun(page, "DISPLAY-V11-T14");
  await expect(page.getByText("Rejected", { exact: true }).first()).toBeVisible();
  await openRun(page, "DISPLAY-V11-T15");
  await expect(page.getByText("Late", { exact: true }).first()).toBeVisible();
});

test("T-05 does not report an off-origin package return or deadline countdown as slack", async ({ page }) => {
  await openRun(page, "DISPLAY-V11B-T05");
  await expect(page.locator(".outcome-strip")).toContainText("Custody: Aircraft");
  await expect(page.locator(".outcome-strip")).not.toContainText("Returned");
  await expect(page.locator(".outcome-strip")).toContainText("Not delivered");
  await expect(page.locator(".outcome-strip")).toContainText("Mission ended before handoff");
  await expect(page.locator(".outcome-strip")).not.toContainText(/slack/i);
});

test("completed replay offers Restart and transitions through Play and Pause", async ({ page }) => {
  await openRun(page, "DISPLAY-V11B-T05");
  const control = page.locator("#lifeline-pause");
  await expect(control).toHaveText("Restart");
  await page.locator("#lifeline-speed").selectOption("0.5");
  await control.click();
  await expect(control).toHaveText("Pause");
  await control.click();
  await expect(control).toHaveText("Play");
  await control.click();
  await expect(control).toHaveText("Pause");
});

test("recorded source labels distinguish PX4 and synthetic evidence", async ({ page }) => {
  await openRun(page, "DISPLAY-V11-T01");
  await expect(page.locator(".connection-banner strong")).toHaveText("Synthetic · Recorded replay");
});

test("presentation mode uses native Open MCT pane collapse and is reversible", async ({ page }) => {
  await openRun(page, "DISPLAY-V11-T01", { width: 1366, height: 768 });
  const toggle = page.locator("#lifeline-presentation");
  await toggle.click();
  await expect(page.locator(".l-shell__pane-tree")).toHaveClass(/l-pane--collapsed/);
  await expect(page.locator(".l-shell__pane-inspector")).toHaveClass(/l-pane--collapsed/);
  await expect(page.locator(".map-panel")).toBeInViewport();
  await expect(page.locator(".decision-panel")).toBeInViewport();
  await toggle.click();
  await expect(page.locator(".l-shell__pane-tree")).not.toHaveClass(/l-pane--collapsed/);
  await expect(page.locator(".l-shell__pane-inspector")).not.toHaveClass(/l-pane--collapsed/);
});
