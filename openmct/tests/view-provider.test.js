import assert from "node:assert/strict";
import test from "node:test";

import {
  createAssuranceViewProvider,
  criticalDataStatus,
  escapeHtml
} from "../src/plugins/lifeline/view-provider.js";

test("escapes untrusted evidence text", () => {
  assert.equal(escapeHtml("<script>&"), "&lt;script&gt;&amp;");
});

test("classifies invalid and over-age critical telemetry", () => {
  assert.deepEqual(
    criticalDataStatus({
      operator_link_available_valid: true,
      operator_link_available_age_s: 0,
      navigation_confidence_valid: false,
      navigation_confidence_age_s: 0,
      energy_margin_wh_valid: true,
      energy_margin_wh_age_s: 4
    }),
    { healthy: false, failed: ["navigation", "energy"] }
  );
});

test("service loss replaces the console with an explicit unavailable state", () => {
  let socket;
  globalThis.WebSocket = class {
    constructor() { socket = this; }
    close() {}
  };
  const provider = createAssuranceViewProvider("http://127.0.0.1:8765");
  const view = provider.view();
  const element = { innerHTML: "" };
  view.show(element);
  socket.onerror();
  assert.match(element.innerHTML, /DATA SOURCE UNAVAILABLE/);
  assert.doesNotMatch(element.innerHTML, /state-nominal/);
  view.destroy();
});

test("stale data and incomplete evidence are visible without relying on color", () => {
  let socket;
  globalThis.WebSocket = class {
    constructor() { socket = this; }
    close() {}
  };
  const timers = { setTimeout: () => 1, clearTimeout: () => {} };
  const provider = createAssuranceViewProvider("http://127.0.0.1:8765", { timers });
  const view = provider.view();
  const element = { innerHTML: "" };
  view.show(element);
  socket.onmessage({ data: JSON.stringify({
    message_type: "snapshot",
    payload: {
      run_id: "TEST",
      sim_time_s: 4,
      assurance_state: "UNKNOWN",
      navigation_confidence_valid: true,
      navigation_confidence_age_s: 4,
      energy_margin_wh_valid: true,
      evidence_complete: false,
      evidence_issue_count: 2,
      verification_status: "INCOMPLETE"
    }
  }) });
  assert.match(element.innerHTML, /CRITICAL DATA STALE OR INVALID: navigation/);
  assert.match(element.innerHTML, /INCOMPLETE/);
  assert.match(element.innerHTML, /2 ISSUE\(S\)/);
  view.destroy();
});

test("replay completion preserves the final snapshot and labels recorded data", () => {
  let socket;
  globalThis.WebSocket = class {
    constructor() { socket = this; }
    close() {}
  };
  const timers = { setTimeout: () => 1, clearTimeout: () => {} };
  const view = createAssuranceViewProvider("http://127.0.0.1:8765", { timers }).view();
  const element = { innerHTML: "" };
  view.show(element);
  socket.onmessage({ data: JSON.stringify({
    message_type: "snapshot",
    payload: {
      run_id: "TEST",
      sim_time_s: 23,
      mission_state: "SAFE_STOP",
      assurance_state: "TERMINATE",
      navigation_confidence_valid: true,
      energy_margin_wh_valid: true,
      verification_status: "PASS",
      evidence_complete: true
    }
  }) });
  socket.onmessage({ data: JSON.stringify({
    message_type: "status",
    status: "replay_complete"
  }) });
  assert.match(element.innerHTML, /REPLAY COMPLETE/);
  assert.match(element.innerHTML, /SAFE_STOP/);
  assert.match(element.innerHTML, /PASS/);
  view.destroy();
});
