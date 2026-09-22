export const escapeHtml = (value) => String(value ?? "Unavailable")
  .replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;");

export function stateClass(state) {
  return "state-" + String(state || "unknown").toLowerCase().replaceAll("_", "-");
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

function aircraftOutcome(point) {
  return {
    RECOVERED: "Recovered",
    SAFE_STOP: "Landed and stopped",
    ABORTED: "Run aborted"
  }[point.mission_state] || "In progress";
}

export function humanizeState(value, fallback = "Not available") {
  if (!value) return fallback;
  return String(value).toLowerCase().replaceAll("_", " ").replace(/(^|\s)\S/g, (letter) => letter.toUpperCase());
}

export function actionPresentation(value) {
  if (value === "CONTROLLED_LAND") return "Controlled landing";
  if (value === "NONE") return "No intervention";
  return humanizeState(value);
}

export function playbackControlLabel({ replayComplete = false, paused = false } = {}) {
  if (replayComplete) return "Restart";
  return paused ? "Play" : "Pause";
}

export function timelinessPresentation(point = {}, configuredDeadlineS = null) {
  if (point.delivery_outcome === "NOT_COMPLETED") {
    return { primary: "Not delivered", detail: "Mission ended before handoff." };
  }
  if (point.timeliness === "ON_TIME" || point.timeliness === "LATE") {
    const acceptedAt = Number(point.accepted_at_s);
    const inferredDeadline = Number(point.sim_time_s) + Number(point.deadline_remaining_s);
    const deadline = Number.isFinite(inferredDeadline) ? inferredDeadline : Number(configuredDeadlineS);
    const margin = deadline - acceptedAt;
    const detail = Number.isFinite(margin)
      ? (margin >= 0 ? margin.toFixed(1) + " s before deadline" : Math.abs(margin).toFixed(1) + " s after deadline")
      : "Acceptance recorded; deadline margin unavailable.";
    return { primary: point.timeliness === "ON_TIME" ? "On time" : "Late", detail };
  }
  if (point.timeliness === "PENDING" && point.deadline_remaining_s != null) {
    return {
      primary: "Pending",
      detail: Number(point.deadline_remaining_s).toFixed(1) + " s until delivery deadline"
    };
  }
  if (point.timeliness === "NOT_MODELED") {
    return { primary: "Not modeled", detail: "No delivery deadline model." };
  }
  return { primary: "Unknown", detail: "No supported timeliness disposition." };
}

export function sourcePresentation(source, connectionState = "") {
  const live = String(connectionState).startsWith("LIVE");
  if (source === "px4") return live ? "PX4 SITL · Live" : "PX4 SITL · Recorded replay";
  if (source === "fake") return live ? "Synthetic · Live" : "Synthetic · Recorded replay";
  return live ? "Simulation · Live" : "Simulation · Recorded replay";
}

function mapPosition(north = 0, east = 0) {
  return {
    x: 64 + Math.max(0, Math.min(100, Number(east))) / 100 * 512,
    y: 276 - Math.max(0, Math.min(260, Number(north))) / 260 * 216
  };
}

function routePolyline() {
  return [[0, 0], [120, 35], [240, 80], [0, 0]].map(([north, east]) => {
    const point = mapPosition(north, east);
    return point.x + "," + point.y;
  }).join(" ");
}

function momentExplanation(point = {}) {
  const stale = criticalDataStatus(point).failed;
  return {
    title: "T+" + Number(point.sim_time_s || 0).toFixed(1) + " · " + (point.decision_code || "NO DECISION"),
    known: "Link " + (point.operator_link_available ? "available" : "unavailable") +
      "; navigation " + Number(point.navigation_confidence || 0).toFixed(2) +
      "; modeled energy margin " + Number(point.energy_margin_wh || 0).toFixed(1) + " Wh.",
    unavailable: stale.length ? stale.join(", ") : "No critical input was stale.",
    action: actionPresentation(point.recommended_action || "NONE"),
    rejected: (point.rejected_actions || []).map((item) => actionPresentation(item)).join(", ") || "None recorded",
    delivery: "Delivery " + (point.delivery_outcome || "NOT_MODELED") +
      "; custody " + (point.package_custody || "NOT_MODELED") +
      "; receipt " + (point.receipt_status || "NOT_MODELED") + ".",
    trace: "Requirements " + ((point.requirement_ids || []).join(", ") || "none") +
      "; hazards " + ((point.hazard_ids || []).join(", ") || "none") + "."
  };
}

export function createAssuranceViewProvider(apiBase, options = {}) {
  const staleAfterMs = options.staleAfterMs ?? 3000;
  const timers = options.timers ?? globalThis;
  const runId = options.runId || null;
  let playbackSpeed = options.playbackSpeed ?? 4;
  const streamUrl = (afterSequence = -1) => {
    const values = new URLSearchParams({ after_sequence: String(afterSequence), speed: String(playbackSpeed) });
    if (runId) values.set("run_id", runId);
    return apiBase.replace(/^http/, "ws") + "/api/v1/stream?" + values;
  };
  return {
    key: "lifeline.assurance.view",
    name: "Medical Resupply Mission Lab",
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
      let selectedMoment = null;
      let eventRows = [];
      let breadcrumb = [];
      let runCatalog = [];
      let contract = null;
      let paused = false;
      let history = [];
      let sourceUnavailable = false;
      let presentationMode = false;

      const bindInteractions = () => {
        if (!container?.querySelectorAll) return;
        container.querySelectorAll("[data-moment]").forEach((button) => {
          button.addEventListener("click", () => {
            selectedMoment = eventRows[Number(button.dataset.moment)]?.point || lastPoint;
            render(lastPoint);
          });
        });
        const selector = container.querySelector("#lifeline-run-selector");
        if (selector) selector.addEventListener("change", () => {
          if (!selector.value || selector.value === lastPoint.run_id) return;
          const url = new URL(globalThis.location.href);
          url.searchParams.set("run", selector.value);
          globalThis.location.assign(url);
        });
        const pauseButton = container.querySelector("#lifeline-pause");
        if (pauseButton) pauseButton.addEventListener("click", () => {
          if (replayComplete) {
            socket?.close();
            replayComplete = false;
            paused = false;
            lastSequence = -1;
            lastPoint = {};
            selectedMoment = null;
            eventRows = [];
            breadcrumb = [];
            history = [];
            connectionState = "REPLAY RESTARTING";
            render();
            connectStream();
            return;
          }
          paused = !paused;
          if (paused) {
            connectionState = "REPLAY PAUSED";
            socket?.close();
            render(lastPoint);
          } else {
            selectedMoment = null;
            connectionState = "REPLAY RESUMING";
            connectStream();
          }
        });
        const speedSelector = container.querySelector("#lifeline-speed");
        if (speedSelector) speedSelector.addEventListener("change", () => {
          playbackSpeed = Number(speedSelector.value);
          if (!paused && !replayComplete) {
            socket?.close();
            connectStream();
          }
        });
        const seek = container.querySelector("#lifeline-seek");
        if (seek) seek.addEventListener("input", () => {
          selectedMoment = history[Number(seek.value)] || lastPoint;
          render(lastPoint);
        });
        const presentationButton = container.querySelector("#lifeline-presentation");
        if (presentationButton) presentationButton.addEventListener("click", () => {
          presentationMode = !presentationMode;
          if (!presentationMode) {
            globalThis.document?.querySelector(
              ".l-shell__pane-tree.l-pane--collapsed > .l-pane__expand-button"
            )?.click();
            globalThis.document?.querySelector(
              ".l-shell__pane-inspector.l-pane--collapsed > .l-pane__expand-button"
            )?.click();
            render(lastPoint);
            return;
          }
          const [path, query = ""] = globalThis.location.hash.split("?");
          const params = new URLSearchParams(query);
          params.set("hideTree", "true");
          params.set("hideInspector", "true");
          globalThis.location.hash = path + (params.size ? "?" + params.toString() : "");
          render(lastPoint);
        });
      };

      const render = (point = {}) => {
        if (!container) return;
        point = selectedMoment || point;
        const e = escapeHtml;
        const nav = Number(point.navigation_confidence ?? 0);
        const energy = Number(point.energy_margin_wh ?? 0);
        const critical = criticalDataStatus(point);
        const verificationStatus = point.verification_status || "PENDING";
        const integrityStatus = point.integrity_status ||
          (point.evidence_complete === true ? "VERIFIED" : point.evidence_complete === false ? "INCOMPLETE" : "PENDING");
        const vehicle = mapPosition(point.north_m, point.east_m);
        const deliverySite = mapPosition(240, 80);
        const packagePosition = point.package_custody === "RECEIVING_STATION" ? deliverySite : vehicle;
        const moment = momentExplanation(selectedMoment || point);
        const packageInfo = contract?.package || {};
        const manifest = packageInfo.manifest || [];
        const selectedSequence = Number(point.sequence ?? Number.MAX_SAFE_INTEGER);
        const selectedRun = runCatalog.find((item) => item.run_id === point.run_id);
        const sourceLabel = sourcePresentation(selectedRun?.source, connectionState);
        const timeliness = timelinessPresentation(point, contract?.delivery_deadline_s);
        const actionLabel = actionPresentation(point.recommended_action);
        const integrityIssues = Number(point.evidence_issue_count || 0);
        const presentationLabel = presentationMode ? "Exit presentation" : "Presentation mode";
        const breadcrumbPoints = history
          .filter((item) => Number(item.sequence) <= selectedSequence)
          .map((item) => mapPosition(item.north_m, item.east_m))
          .filter((item, index, items) => index === 0 || Math.hypot(item.x - items[index - 1].x, item.y - items[index - 1].y) > 4)
          .map((item) => item.x + "," + item.y)
          .join(" ");
        const runs = runCatalog.slice(0, 40).map((item) =>
          "<option value='" + e(item.run_id) + "' " + (item.run_id === point.run_id ? "selected" : "") + ">" +
          e(item.scenario_id) + " · " + e(item.source === "px4" ? "PX4 SITL" : item.source === "fake" ? "Synthetic" : "Simulation") +
          " · " + e(String(item.run_id).split("-").at(-1)) + "</option>"
        ).join("");
        const manifestRows = manifest.map((item) =>
          "<li><b>" + Number(item.quantity) + " " + e(item.unit) + "</b> " + e(item.description) + "</li>"
        ).join("") || "<li>Legacy run: delivery was not modeled.</li>";
        const visibleEventRows = eventRows.filter((row) => Number(row.point.sequence) <= selectedSequence);
        const timelineRows = visibleEventRows.slice(-10).map((row) => {
          const actualIndex = eventRows.indexOf(row);
          const selected = row.point.sequence === point.sequence ? " is-selected" : "";
          return "<button data-moment='" + actualIndex + "' class='moment-row" + selected + "'><time>T+" +
            Number(row.point.sim_time_s).toFixed(1) + "</time><span>" + e(row.point.mission_state) +
            "</span><span>" + e(row.point.package_custody || "NOT_MODELED") + "</span><b>" +
            e(row.point.decision_code) + "</b></button>";
        }).join("");
        container.innerHTML =
          "<section class='lifeline-shell" + (presentationMode ? " is-presentation" : "") + "'>" +
            "<header class='mission-header'><div><span class='eyebrow'>SIMULATION · MEDICAL RESUPPLY MISSION LAB</span>" +
              "<h1>" + e(contract?.recipient?.name ? contract.recipient.name + " Resupply" : "Project Lifeline") + "</h1><p>" +
              e(contract?.origin?.name || "Logistics Point Alpha") + " → " +
              e(contract?.recipient?.name || "Echo Aid Station") + " · <span class='machine-id'>" +
              e(contract?.mission_id || point.mission_id) + "</span></p></div>" +
              "<div class='mission-meta'><label>Recorded mission<select id='lifeline-run-selector' aria-label='Select recorded mission'>" +
              (runs || "<option>" + e(point.run_id) + "</option>") + "</select></label><b>T+" +
              Number(point.sim_time_s || 0).toFixed(1) + " s</b><span class='run-id'>" + e(point.run_id) + "</span></div></header>" +
            "<div class='connection-banner'><strong>" + e(sourceLabel) + "</strong><span>" + e(connectionState) + "</span></div>" +
            "<nav class='replay-controls' aria-label='Replay controls'><button id='lifeline-pause' type='button'>" +
              playbackControlLabel({ replayComplete, paused }) + "</button><label>Speed<select id='lifeline-speed'>" +
              [0.5, 1, 2, 4].map((value) => "<option value='" + value + "' " + (value === playbackSpeed ? "selected" : "") + ">" + value + "×</option>").join("") +
              "</select></label><label class='seek-label'>Inspect recorded moment<input id='lifeline-seek' type='range' min='0' max='" +
              Math.max(0, history.length - 1) + "' value='" + Math.max(0, selectedMoment ? history.indexOf(selectedMoment) : history.length - 1) + "'></label>" +
              "<button id='lifeline-presentation' type='button'>" + e(presentationLabel) + "</button></nav>" +
            (point.exploratory ? "<div class='exploratory'>EXPLORATORY: NOT CONTROLLED VERIFICATION EVIDENCE</div>" : "") +
            (critical.healthy ? "" : "<div class='critical-stale'>CRITICAL DATA STALE OR INVALID: " + e(critical.failed.join(", ")) + "</div>") +
            "<div class='outcome-strip'>" +
              "<article><label>Aircraft</label><strong>" + e(aircraftOutcome(point)) + "</strong><small>Recorded state: " + e(point.mission_state) + "</small></article>" +
              "<article class='" + stateClass(point.delivery_outcome) + "'><label>Delivery</label><strong>" + e(humanizeState(point.delivery_outcome, "Not modeled")) + "</strong><small>Custody: " + e(humanizeState(point.package_custody, "Not modeled")) + "</small></article>" +
              "<article class='" + stateClass(point.timeliness) + "'><label>Timeliness</label><strong>" + e(timeliness.primary) + "</strong><small>" + e(timeliness.detail) + "</small></article>" +
              "<article class='" + stateClass(point.assurance_state) + "'><label>Assurance response</label><strong>" + e(actionLabel) + "</strong><small>Supervisor state: " + e(humanizeState(point.assurance_state)) + "</small></article>" +
              "<article class='verification-" + String(verificationStatus).toLowerCase() + "'><label>Evidence integrity</label><strong>" + e(humanizeState(integrityStatus)) + "</strong><small>Behavior verification: " + e(humanizeState(verificationStatus)) + (integrityIssues ? " · " + integrityIssues + " integrity issue(s)" : "") + "</small></article>" +
            "</div>" +
            "<div class='mission-grid'>" +
              "<article class='panel map-panel'><div class='panel-heading'><div><span>LOCAL NED · FICTIONAL COORDINATES</span><h2>Mission map</h2></div><b>" +
                Number(point.north_m || 0).toFixed(0) + " m N · " + Number(point.east_m || 0).toFixed(0) + " m E</b></div>" +
                "<svg viewBox='0 0 640 320' role='img' aria-label='Telemetry-driven fictional local NED mission route'>" +
                  "<defs><pattern id='grid' width='40' height='40' patternUnits='userSpaceOnUse'><path d='M 40 0 L 0 0 0 40' class='map-grid'/></pattern></defs>" +
                  "<rect x='28' y='28' width='584' height='264' rx='18' class='map-ground'/><rect x='28' y='28' width='584' height='264' rx='18' fill='url(#grid)'/>" +
                  "<polyline points='" + routePolyline() + "' class='route'/>" +
                  (breadcrumbPoints ? "<polyline points='" + breadcrumbPoints + "' class='breadcrumb'/>" : "") +
                  "<circle cx='64' cy='276' r='10' class='site'/><text x='48' y='306'>LOGISTICS POINT</text>" +
                  "<circle cx='" + deliverySite.x + "' cy='" + deliverySite.y + "' r='34' class='delivery-zone'/>" +
                  "<circle cx='" + deliverySite.x + "' cy='" + deliverySite.y + "' r='10' class='delivery'/><text x='" + (deliverySite.x - 74) + "' y='" + (deliverySite.y - 48) + "'>ECHO AID STATION</text>" +
                  "<g transform='translate(" + vehicle.x + " " + vehicle.y + ")'><path d='M0 -14 L11 11 L0 7 L-11 11 Z' class='vehicle'/></g>" +
                  "<g transform='translate(" + (packagePosition.x + 18) + " " + (packagePosition.y + 12) + ")'><rect x='-7' y='-7' width='14' height='14' rx='2' class='package'/><text x='12' y='5'>PACKAGE</text></g>" +
                  "<text x='44' y='50' class='axis-label'>N ↑</text><text x='552' y='284' class='axis-label'>E →</text>" +
                "</svg><div class='map-legend'><span><i class='legend-aircraft'></i>Aircraft telemetry</span><span><i class='legend-package'></i>Package custody</span><span><i class='legend-zone'></i>Receiving area</span></div></article>" +
              "<article class='panel request-panel'><div class='panel-heading'><div><span>REQUEST → PACKAGE → RECEIPT</span><h2>Supply request</h2></div><b>" + e(point.request_id || "LEGACY") + "</b></div>" +
                "<dl class='request-facts'><dt>Package</dt><dd>" + e(packageInfo.description || point.package_id || "Delivery not modeled") + "</dd><dt>Assigned ID</dt><dd>" + e(point.package_id) +
                "</dd><dt>Mass</dt><dd>" + (packageInfo.mass_kg ? Number(packageInfo.mass_kg).toFixed(1) + " kg · planning assumption" : "Not modeled") +
                "</dd><dt>Recipient</dt><dd>" + e(contract?.recipient?.name || point.recipient_id) + "</dd><dt>Custody</dt><dd>" + e(point.package_custody || "NOT_MODELED") +
                "</dd><dt>Receipt</dt><dd>" + e(point.receipt_status || "NOT_MODELED") + "</dd></dl>" +
                "<div class='handoff'><span>Modeled unloading / handoff</span><b>" + (Number(point.handoff_progress || 0) * 100).toFixed(0) +
                "%</b><progress max='1' value='" + Number(point.handoff_progress || 0) + "'></progress></div>" +
                "<details><summary>Manifest · " + manifest.length + " line items</summary><ul>" + manifestRows + "</ul></details></article>" +
              "<article class='panel resources-panel'><div class='panel-heading'><div><span>MEASURED + MODELED</span><h2>Aircraft resources</h2></div><b>" + e(point.flight_mode) + "</b></div>" +
                "<div class='metric'><span>Operator link</span><b>" + (point.operator_link_available ? "AVAILABLE" : "UNAVAILABLE") + "</b></div>" +
                "<div class='metric'><span>Navigation confidence · modeled</span><b>" + nav.toFixed(2) + "</b><progress max='1' value='" + nav + "'></progress></div>" +
                "<div class='metric'><span>Battery · simulator source</span><b>" + Number(point.battery_remaining_pct || 0).toFixed(1) + "%</b><progress max='100' value='" + Number(point.battery_remaining_pct || 0) + "'></progress></div>" +
                "<div class='energy-row'><div><small>Available</small><b>" + Number(point.energy_available_wh || 0).toFixed(1) + " Wh</b></div><div><small>Recovery demand</small><b>" + Number(point.energy_recovery_wh || 0).toFixed(1) +
                " Wh</b></div><div><small>Reserve</small><b>" + Number(point.energy_reserve_wh || 0).toFixed(1) + " Wh</b></div><div><small>Margin</small><b>" + energy.toFixed(1) + " Wh</b></div></div>" +
                "<p class='provenance'>Energy feasibility and confidence are Lifeline models; position, altitude, battery, and mode are simulator telemetry in SITL runs.</p></article>" +
              "<article class='panel decision-panel'><div class='panel-heading'><div><span>CONSTRAINED POLICY</span><h2>Explain this moment</h2></div><b class='decision-code'>" + e(point.decision_code) + "</b></div>" +
                "<div class='action-callout'><span>Selected action</span><strong>" + e(actionLabel) + "</strong><small>Supervisor state: " + e(humanizeState(point.assurance_state)) + "</small></div><p>" + e(point.decision_summary) + "</p>" +
                "<dl><dt>Observed aircraft</dt><dd>" + e(humanizeState(point.mission_state)) + "</dd><dt>Rejected</dt><dd>" + e((point.rejected_actions || []).map((item) => humanizeState(item)).join(", ") || "None") + "</dd><dt>Requirements</dt><dd>" + e((point.requirement_ids || []).join(", ")) +
                "</dd><dt>Hazards</dt><dd>" + e((point.hazard_ids || []).join(", ")) + "</dd></dl></article>" +
            "</div>" +
            "<div class='lower-grid'><article class='panel timeline-panel'><div class='panel-heading'><div><span>SELECT AN EVENT</span><h2>Coordinated mission timeline</h2></div><b>" + visibleEventRows.length + " transitions</b></div><div class='events'>" + timelineRows + "</div></article>" +
              "<article class='panel explain-panel'><div class='panel-heading'><div><span>TECHNICAL DETAIL</span><h2>Decision context</h2></div></div><h3>" + e(moment.title) + "</h3>" +
              "<dl><dt>System knew</dt><dd>" + e(moment.known) + "</dd><dt>Unavailable</dt><dd>" + e(moment.unavailable) + "</dd><dt>Allowed action</dt><dd>" + e(moment.action) +
              "</dd><dt>Rejected</dt><dd>" + e(moment.rejected) + "</dd><dt>Resupply objective</dt><dd>" + e(moment.delivery) + "</dd><dt>Trace</dt><dd>" + e(moment.trace) + "</dd></dl></article></div>" +
          "</section>";
        bindInteractions();
      };

      const renderUnavailable = (reason) => {
        if (!container || replayComplete) return;
        sourceUnavailable = true;
        connectionState = reason;
        container.innerHTML = "<div class='lifeline-unavailable'>" + escapeHtml(reason) + ". Telemetry is not assumed healthy.</div>";
      };
      const armWatchdog = () => {
        if (watchdog) timers.clearTimeout(watchdog);
        watchdog = timers.setTimeout(() => renderUnavailable("DATA SOURCE STALE"), staleAfterMs);
      };
      const loadReferenceData = async () => {
        if (typeof fetch !== "function") return;
        try {
          const [contractResponse, runsResponse] = await Promise.all([
            fetch(apiBase + "/api/v1/mission-contract"),
            fetch(apiBase + "/api/v1/runs")
          ]);
          if (contractResponse.ok) contract = await contractResponse.json();
          if (runsResponse.ok) runCatalog = await runsResponse.json();
          if (!sourceUnavailable) render(lastPoint);
        } catch {
          // The stream remains usable if catalogue metadata is unavailable.
        }
      };
      const connectStream = () => {
        replayComplete = false;
        socket = new WebSocket(streamUrl(lastSequence));
        socket.onopen = () => {
          connectionState = "REPLAY STREAM · " + playbackSpeed + "×";
          armWatchdog();
        };
        socket.onmessage = handleMessage;
        socket.onerror = () => renderUnavailable("DATA SOURCE UNAVAILABLE");
        socket.onclose = () => {
          if (destroyed || replayComplete || paused) return;
          const terminal = ["RECOVERED", "SAFE_STOP", "ABORTED"].includes(lastPoint.mission_state);
          if (terminal && lastPoint.evidence_complete) {
            replayComplete = true;
            connectionState = "REPLAY COMPLETE";
            if (watchdog) timers.clearTimeout(watchdog);
            render(lastPoint);
          } else {
            renderUnavailable("DATA SOURCE DISCONNECTED");
          }
        };
      };
      const handleMessage = (event) => {
        const message = JSON.parse(event.data);
        const status = message.status || message.payload?.status;
        if (message.message_type === "status") {
          if (String(status).toLowerCase() === "replay_complete") {
            replayComplete = true;
            connectionState = "REPLAY COMPLETE";
            if (watchdog) timers.clearTimeout(watchdog);
          } else if (status) {
            connectionState = "LIVE · " + String(status).toUpperCase();
          }
          render(lastPoint);
          return;
        }
        if (message.message_type !== "snapshot" || Number(message.sequence) <= lastSequence) return;
        lastSequence = Number(message.sequence);
        armWatchdog();
        const point = message.payload;
        sourceUnavailable = false;
        history.push(structuredClone(point));
        const previous = lastPoint;
        const changed = previous.sequence == null ||
          previous.mission_state !== point.mission_state ||
          previous.package_custody !== point.package_custody ||
          previous.receipt_status !== point.receipt_status ||
          previous.decision_code !== point.decision_code;
        if (changed) eventRows.push({ point: structuredClone(point) });
        const position = mapPosition(point.north_m, point.east_m);
        const prior = breadcrumb.at(-1);
        if (!prior || Math.hypot(position.x - prior.x, position.y - prior.y) > 4) breadcrumb.push(position);
        lastPoint = point;
        if (!selectedMoment) render(point);
        else render(lastPoint);
      };
      return {
        show(element) {
          container = element;
          const hashQuery = globalThis.location?.hash?.split("?")[1] || "";
          const hashParams = new URLSearchParams(hashQuery);
          presentationMode = hashParams.get("hideTree") === "true" &&
            hashParams.get("hideInspector") === "true";
          render();
          void loadReferenceData();
          connectStream();
        },
        destroy() {
          if (watchdog) timers.clearTimeout(watchdog);
          destroyed = true;
          socket?.close();
          container = undefined;
          eventRows = [];
          breadcrumb = [];
          history = [];
          lastPoint = {};
        }
      };
    }
  };
}
