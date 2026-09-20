import openmct from "openmct";
import "../node_modules/openmct/dist/espressoTheme.css";
import "./styles.css";
import LifelinePlugin from "./plugins/lifeline/install.js";

export function selectedRun(search = globalThis.location?.search || "") {
  const runId = new URLSearchParams(search).get("run");
  if (runId && !/^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/.test(runId)) {
    throw new Error("Unsafe Lifeline run identifier");
  }
  return runId;
}

const epoch = Date.UTC(2026, 0, 1);

openmct.setAssetPath("/node_modules/openmct/dist");
openmct.install(openmct.plugins.LocalStorage());
openmct.install(openmct.plugins.MyItems());
openmct.install(openmct.plugins.UTCTimeSystem());
openmct.install(openmct.plugins.Conductor({
  menuOptions: [{
    name: "Recorded mission",
    timeSystem: "utc",
    bounds: { start: epoch, end: epoch + 120_000 }
  }]
}));
openmct.install(openmct.plugins.Espresso());
openmct.install(openmct.plugins.SummaryWidget());
openmct.install(
  LifelinePlugin({
    apiBase: import.meta.env.VITE_LIFELINE_API_BASE || "http://127.0.0.1:8765",
    runId: selectedRun()
  })
);

document.addEventListener("DOMContentLoaded", () => openmct.start());
