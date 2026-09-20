import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./tests",
  testMatch: /display-qualification\.spec\.js/,
  timeout: 45_000,
  fullyParallel: false,
  workers: 1,
  reporter: [["line"], ["./tests/display-reporter.js"]],
  use: {
    baseURL: "http://127.0.0.1:8876",
    browserName: "chromium",
    trace: "retain-on-failure"
  },
  webServer: [
    {
      command: "node tests/start-api.js",
      url: "http://127.0.0.1:8875/api/v1/health",
      reuseExistingServer: !process.env.CI,
      timeout: 30_000
    },
    {
      command: "npm run dev -- --port 8876 --mode qualification",
      url: "http://127.0.0.1:8876",
      reuseExistingServer: !process.env.CI,
      timeout: 30_000
    }
  ]
});
