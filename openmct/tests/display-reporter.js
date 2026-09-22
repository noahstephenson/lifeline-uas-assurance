import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import { execFileSync } from "node:child_process";
import { chromium } from "@playwright/test";

const root = path.resolve(process.cwd(), "..");
const output = path.join(root, "evidence", "display-qualification");
const fixtures = ["DISPLAY-V11-T01", "DISPLAY-V11-T05", "DISPLAY-V11-T11", "DISPLAY-V11-T13", "DISPLAY-V11-T14", "DISPLAY-V11-T15"];

export default class DisplayQualificationReporter {
  constructor() {
    this.assertions = [];
  }

  onTestEnd(test, result) {
    this.assertions.push({
      name: test.titlePath().join(" / "),
      status: result.status,
      passed: result.status === "passed",
      duration_ms: result.duration,
      error: result.error?.message || null
    });
  }

  async onEnd(result) {
    fs.mkdirSync(output, { recursive: true });
    const browser = await chromium.launch({ headless: true });
    const browserVersion = browser.version();
    await browser.close();
    let commit = "unavailable";
    try {
      commit = execFileSync("git", ["rev-parse", "HEAD"], { cwd: root, encoding: "utf8" }).trim();
    } catch {}
    const screenshotsDir = path.join(output, "screenshots");
    const screenshotHashes = fs.existsSync(screenshotsDir)
      ? Object.fromEntries(listFiles(screenshotsDir)
        .filter((file) => fixtures.some((runId) => path.basename(file).startsWith(`${runId}-`)))
        .map((file) => [path.relative(output, file).replaceAll("\\", "/"), sha(file)]))
      : {};
    const report = {
      schema_version: "1.0",
      qualification_method: "automated browser display qualification",
      human_usability_study: false,
      verification_status: result.status === "passed" && this.assertions.every((item) => item.passed) ? "PASS" : "FAIL",
      generated_at: new Date().toISOString(),
      commit,
      playwright_version: JSON.parse(fs.readFileSync(path.join(process.cwd(), "node_modules", "@playwright", "test", "package.json"))).version,
      browser: { name: "chromium", version: browserVersion },
      viewports: ["1440x900", "800x1000"],
      fixtures: Object.fromEntries(fixtures.map((runId) => [runId, directoryHash(path.join(root, "evidence", "runs", runId))])),
      screenshots: screenshotHashes,
      assertions: this.assertions
    };
    fs.writeFileSync(path.join(output, "display-qualification.json"), `${JSON.stringify(report, null, 2)}\n`);
  }
}

function listFiles(directory) {
  return fs.readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const item = path.join(directory, entry.name);
    return entry.isDirectory() ? listFiles(item) : [item];
  }).sort();
}

function sha(file) {
  return crypto.createHash("sha256").update(fs.readFileSync(file)).digest("hex");
}

function directoryHash(directory) {
  const hash = crypto.createHash("sha256");
  for (const file of listFiles(directory)) {
    hash.update(path.relative(directory, file).replaceAll("\\", "/"));
    hash.update(sha(file));
  }
  return hash.digest("hex");
}
