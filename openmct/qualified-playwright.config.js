import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./tests",
  testMatch: /qualified-replay\.spec\.js/,
  timeout: 60_000,
  fullyParallel: false,
  workers: 1,
  reporter: "line",
  use: {
    baseURL: "http://127.0.0.1:8876",
    browserName: "chromium"
  },
  webServer: [
    {
      command: "node tests/start-api.js",
      url: "http://127.0.0.1:8875/api/v1/health",
      reuseExistingServer: false,
      timeout: 30_000
    },
    {
      command: "npm run dev -- --port 8876 --mode qualification",
      url: "http://127.0.0.1:8876",
      env: {
        VITE_LIFELINE_API_BASE: "http://127.0.0.1:8875",
        VITE_LIFELINE_REPLAY_SPEED: "16"
      },
      reuseExistingServer: false,
      timeout: 30_000
    }
  ]
});
