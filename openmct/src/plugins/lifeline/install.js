import { createAssuranceViewProvider } from "./view-provider.js";

const namespace = "lifeline";
const rootKey = "mission-assurance";
const epoch = Date.UTC(2026, 0, 1);

export default function LifelinePlugin(options = {}) {
  const apiBase = options.apiBase || "http://127.0.0.1:8765";
  return function install(openmct) {
    let dictionaryPromise;
    const dictionary = () => {
      if (!dictionaryPromise) {
        dictionaryPromise = fetch(`${apiBase}/api/v1/metadata`).then((response) => {
          if (!response.ok) throw new Error(`metadata request failed: ${response.status}`);
          return response.json();
        });
      }
      return dictionaryPromise;
    };

    openmct.types.addType("lifeline.telemetry", {
      name: "Lifeline telemetry",
      description: "Requirement-linked UAS simulation telemetry",
      cssClass: "icon-telemetry"
    });
    openmct.types.addType("lifeline.assurance", {
      name: "Mission Assurance",
      description: "Read-only Project Lifeline assurance console",
      cssClass: "icon-object"
    });
    openmct.objects.addRoot({ namespace, key: rootKey });
    openmct.objects.addProvider(namespace, {
      get(identifier) {
        if (identifier.key === rootKey) {
          return Promise.resolve({
            identifier,
            name: "Project Lifeline",
            type: "lifeline.assurance",
            location: "ROOT"
          });
        }
        return dictionary().then((data) => {
          const item = data.measurements.find((measurement) => measurement.key === identifier.key);
          if (!item) throw new Error(`unknown Lifeline object: ${identifier.key}`);
          return {
            identifier,
            name: item.name,
            type: "lifeline.telemetry",
            location: `${namespace}:${rootKey}`,
            telemetry: {
              values: [
                { key: "timestamp", name: "Mission Time", format: "utc", hints: { domain: 1 } },
                { key: "value", name: item.name, format: item.format, units: item.unit, hints: { range: 1 } }
              ]
            }
          };
        });
      }
    });
    openmct.composition.addProvider({
      appliesTo(domainObject) {
        return domainObject.identifier?.namespace === namespace && domainObject.identifier.key === rootKey;
      },
      load() {
        return dictionary().then((data) => data.measurements.map((item) => ({ namespace, key: item.key })));
      }
    });

    const listeners = new Map();
    let socket;
    const connect = () => {
      if (socket && socket.readyState <= 1) return;
      socket = new WebSocket(`${apiBase.replace(/^http/, "ws")}/api/v1/stream`);
      socket.onmessage = (event) => {
        const message = JSON.parse(event.data);
        if (message.message_type !== "snapshot") return;
        for (const [key, callbacks] of listeners.entries()) {
          const point = { id: key, timestamp: epoch + message.sim_time_s * 1000, value: message.payload[key] };
          callbacks.forEach((callback) => callback(point));
        }
      };
    };
    openmct.telemetry.addProvider({
      supportsRequest(domainObject) {
        return domainObject.type === "lifeline.telemetry";
      },
      request(domainObject, requestOptions) {
        const key = domainObject.identifier.key;
        const start = Math.max(0, (requestOptions.start - epoch) / 1000);
        const end = Math.max(start, (requestOptions.end - epoch) / 1000);
        return fetch(`${apiBase}/api/v1/history?key=${encodeURIComponent(key)}&start=${start}&end=${end}`)
          .then((response) => response.json())
          .then((points) => points.map((point) => ({ ...point, timestamp: epoch + point.timestamp })));
      },
      supportsSubscribe(domainObject) {
        return domainObject.type === "lifeline.telemetry";
      },
      subscribe(domainObject, callback) {
        const key = domainObject.identifier.key;
        const callbacks = listeners.get(key) || new Set();
        callbacks.add(callback);
        listeners.set(key, callbacks);
        connect();
        return () => {
          callbacks.delete(callback);
          if (!callbacks.size) listeners.delete(key);
        };
      }
    });
    openmct.objectViews.addProvider(createAssuranceViewProvider(apiBase));
  };
}
