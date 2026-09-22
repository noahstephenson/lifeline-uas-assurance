import assert from "node:assert/strict";
import test from "node:test";

import {
  createAssuranceViewProvider,
  criticalDataStatus,
  escapeHtml,
  playbackControlLabel,
  sourcePresentation,
  timelinessPresentation
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

test("uses unambiguous replay controls and source labels", () => {
  assert.equal(playbackControlLabel(), "Pause");
  assert.equal(playbackControlLabel({ paused: true }), "Play");
  assert.equal(playbackControlLabel({ replayComplete: true }), "Restart");
  assert.equal(sourcePresentation("px4", "REPLAY COMPLETE"), "PX4 SITL · Recorded replay");
  assert.equal(sourcePresentation("px4", "LIVE · RUNNING"), "PX4 SITL · Live");
  assert.equal(sourcePresentation("fake", "REPLAY COMPLETE"), "Synthetic · Recorded replay");
});

test("separates deadline countdown, accepted margin, and non-delivery", () => {
  assert.deepEqual(
    timelinessPresentation({ timeliness: "PENDING", deadline_remaining_s: 65 }),
    { primary: "Pending", detail: "65.0 s until delivery deadline" }
  );
  assert.deepEqual(
    timelinessPresentation({
      delivery_outcome: "ACCEPTED",
      timeliness: "LATE",
      accepted_at_s: 48,
      sim_time_s: 90,
      deadline_remaining_s: -47
    }),
    { primary: "Late", detail: "5.0 s after deadline" }
  );
  assert.deepEqual(
    timelinessPresentation({ delivery_outcome: "NOT_COMPLETED", timeliness: "UNKNOWN" }),
    { primary: "Not delivered", detail: "Mission ended before handoff." }
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
    message_type: "snapshot", sequence: 1,
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
  assert.match(element.innerHTML, /Behavior verification: Incomplete/);
  assert.match(element.innerHTML, /2 integrity issue\(s\)/);
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
    message_type: "snapshot", sequence: 1,
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
  assert.match(element.innerHTML, />Restart</);
  assert.match(element.innerHTML, /SAFE_STOP/);
  assert.match(element.innerHTML, /Evidence integrity/);
  assert.match(element.innerHTML, /Behavior verification: Pass/);
  view.destroy();
});
