import openmct from "openmct";
import "../node_modules/openmct/dist/espressoTheme.css";
import "./styles.css";
import LifelinePlugin from "./plugins/lifeline/install.js";

openmct.setAssetPath("/node_modules/openmct/dist");
openmct.install(openmct.plugins.LocalStorage());
openmct.install(openmct.plugins.MyItems());
openmct.install(openmct.plugins.UTCTimeSystem());
openmct.install(openmct.plugins.Conductor());
openmct.install(openmct.plugins.Espresso());
openmct.install(openmct.plugins.SummaryWidget());
openmct.install(
  LifelinePlugin({ apiBase: import.meta.env.VITE_LIFELINE_API_BASE || "http://127.0.0.1:8765" })
);

const epoch = Date.UTC(2026, 0, 1);
openmct.time.setTimeSystem("utc");
openmct.time.setBounds({ start: epoch, end: epoch + 70_000 });
document.addEventListener("DOMContentLoaded", () => openmct.start());
