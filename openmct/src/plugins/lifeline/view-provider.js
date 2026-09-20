export const escapeHtml = (value) => String(value ?? "—")
  .replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;");

export function stateClass(state) {
  return `state-${String(state || "unknown").toLowerCase()}`;
}

export function criticalDataStatus(point = {}) {
  const checks = [
    ["operator link", point.operator_link_available_valid, point.operator_link_available_age_s, 2],
    ["navigation", point.navigation_confidence_valid, point.navigation_confidence_age_s, 2],
    ["energy", point.energy_margin_wh_valid, point.energy_margin_wh_age_s, 3]
  ];
  const failed = checks
    .filter(([, valid, age, limit]) => valid === false || Number(age ?? 0) > limit)
    .map(([name]) => name);
  return { healthy: failed.length === 0, failed };
}

export function createAssuranceViewProvider(apiBase, options = {}) {
  const staleAfterMs = options.staleAfterMs ?? 3000;
  const timers = options.timers ?? globalThis;
  const runId = options.runId || null;
  const streamUrl = (afterSequence = -1) => {
    const values = new URLSearchParams({ after_sequence: String(afterSequence) });
    if (runId) values.set("run_id", runId);
    return `${apiBase.replace(/^http/, "ws")}/api/v1/stream?${values}`;
  };
  return {
    key: "lifeline.assurance.view",
    name: "Mission Assurance",
    cssClass: "icon-object",
    canView(domainObject) {
      return domainObject.type === "lifeline.assurance";
    },
    view() {
      let container;
      let socket;
      let watchdog;
      let replayComplete = false;
      let destroyed = false;
      let lastSequence = -1;
      let connectionState = "CONNECTING";
      let lastPoint = {};
      let decisionRows = [];
      const render = (point = {}) => {
        if (!container) return;
        const nav = Number(point.navigation_confidence ?? 0);
        const energy = Number(point.energy_margin_wh ?? 0);
        const progress = Number(point.route_progress ?? 0);
        const critical = criticalDataStatus(point);
        const evidenceStatus = point.verification_status || "PENDING";
        container.innerHTML = `
          <section class="lifeline-shell">
            <header class="lifeline-header">
              <div><span class="eyebrow">SIMULATION · REQUIREMENT-LINKED TELEMETRY</span><h1>Project Lifeline</h1></div>
              <div class="run-chip">${escapeHtml(point.run_id)}</div>
            </header>
            <div class="connection-banner connection-${connectionState.toLowerCase()}">${escapeHtml(connectionState)}</div>
            ${point.exploratory ? '<div class="exploratory">EXPLORATORY — NOT CONTROLLED VERIFICATION EVIDENCE</div>' : ""}
            ${critical.healthy ? "" : `<div class="critical-stale">CRITICAL DATA STALE OR INVALID: ${escapeHtml(critical.failed.join(", "))}</div>`}
            <div class="state-grid">
              <article><label>Mission phase</label><strong>${escapeHtml(point.mission_state)}</strong></article>
              <article class="${stateClass(point.assurance_state)}"><label>Assurance state</label><strong>${escapeHtml(point.assurance_state)}</strong></article>
              <article><label>Selected action</label><strong>${escapeHtml(point.recommended_action)}</strong></article>
              <article class="verification-${String(evidenceStatus).toLowerCase()}"><label>Evidence</label><strong>${escapeHtml(evidenceStatus)}</strong><small>${point.evidence_complete ? "COMPLETE" : `${Number(point.evidence_issue_count || 0)} ISSUE(S)`}</small></article>
            </div>
            <div class="main-grid">
              <article class="panel health-panel">
                <h2>Resource health</h2>
                <div class="metric"><span>Operator link</span><b>${point.operator_link_available ? "AVAILABLE" : "UNAVAILABLE"}</b></div>
                <div class="metric"><span>Navigation confidence</span><b>${nav.toFixed(2)}</b><progress max="1" value="${nav}"></progress></div>
                <div class="metric"><span>Energy margin</span><b>${energy.toFixed(1)} Wh</b><progress max="35" value="${Math.max(0, energy)}"></progress></div>
                <div class="metric"><span>Data age</span><b>${Number(point.navigation_confidence_age_s || 0).toFixed(1)} s</b></div>
              </article>
              <article class="panel route-panel">
                <h2>Fictional medical-resupply route</h2>
                <svg viewBox="0 0 600 220" role="img" aria-label="Fictional route progress">
                  <path d="M55 175 C170 130 270 100 350 60 S500 35 545 55" class="route"/>
                  <circle cx="55" cy="175" r="9" class="site"/><text x="42" y="205">Launch</text>
                  <circle cx="545" cy="55" r="9" class="delivery"/><text x="500" y="30">Aid station</text>
                  <circle cx="${55 + progress * 490}" cy="${175 - progress * 120}" r="12" class="vehicle"/>
                </svg>
                <div class="progress-label"><span>Route progress</span><b>${(progress * 100).toFixed(0)}%</b></div>
              </article>
              <article class="panel decision-panel">
                <h2>Decision rationale</h2>
                <div class="decision-code">${escapeHtml(point.decision_code)}</div>
                <p>${escapeHtml(point.decision_summary)}</p>
                <dl><dt>Requirements</dt><dd>${escapeHtml((point.requirement_ids || []).join(", "))}</dd>
                <dt>Hazards</dt><dd>${escapeHtml((point.hazard_ids || []).join(", "))}</dd>
                <dt>Rejected</dt><dd>${escapeHtml((point.rejected_actions || []).join(", "))}</dd></dl>
              </article>
              <article class="panel event-panel">
                <h2>Decision timeline</h2>
                <div class="events">${decisionRows.slice(-6).reverse().map((row) => `
                  <div><time>T+${Number(row.sim_time_s).toFixed(1)}</time><span class="${stateClass(row.assurance_state)}">${escapeHtml(row.assurance_state)}</span><b>${escapeHtml(row.decision_code)}</b></div>`).join("")}</div>
              </article>
            </div>
          </section>`;
      };
      const renderUnavailable = (reason) => {
        if (!container || replayComplete) return;
        connectionState = reason;
        container.innerHTML = `<div class="lifeline-unavailable">${escapeHtml(reason)} — telemetry is not assumed healthy.</div>`;
      };
      const armWatchdog = () => {
        if (watchdog) timers.clearTimeout(watchdog);
        watchdog = timers.setTimeout(() => renderUnavailable("DATA SOURCE STALE"), staleAfterMs);
      };
      return {
        show(element) {
          container = element;
          render();
          socket = new WebSocket(streamUrl(lastSequence));
          socket.onopen = () => {
            connectionState = "LIVE / REPLAY STREAM";
            armWatchdog();
          };
          socket.onmessage = (event) => {
            const message = JSON.parse(event.data);
            const status = message.status || message.payload?.status;
            if (message.message_type === "status" && String(status).toLowerCase() === "replay_complete") {
              replayComplete = true;
              connectionState = "REPLAY COMPLETE";
              if (watchdog) timers.clearTimeout(watchdog);
              render(lastPoint);
              return;
            }
            if (message.message_type !== "snapshot") return;
            if (Number(message.sequence) <= lastSequence) return;
            lastSequence = Number(message.sequence);
            armWatchdog();
            const point = message.payload;
            lastPoint = point;
            const last = decisionRows.at(-1);
            if (!last || last.decision_code !== point.decision_code) decisionRows.push(point);
            render(point);
          };
          socket.onerror = () => renderUnavailable("DATA SOURCE UNAVAILABLE");
          socket.onclose = () => {
            if (!destroyed && !replayComplete) renderUnavailable("DATA SOURCE DISCONNECTED");
          };
        },
        destroy() {
          if (watchdog) timers.clearTimeout(watchdog);
          destroyed = true;
          socket?.close();
          container = undefined;
          decisionRows = [];
          lastPoint = {};
        }
      };
    }
  };
}
