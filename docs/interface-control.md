# Interface control document

| ID | Producer → consumer | Mechanism | Rate | Failure behavior |
|---|---|---|---|---|
| IF-01 | PX4 → MAVSDK adapter | MAVLink/UDP | native, sampled 2 Hz | source becomes disconnected/stale |
| IF-02 | Scenario → normalizer | typed in-process event | scheduled | reject scenario before run |
| IF-03 | Adapter → normalizer | async sample | 2 Hz | retain value and age; never refresh timestamp |
| IF-04 | Normalizer → assurance | `MissionSnapshot` | 2 Hz | critical invalidity produces `UNKNOWN` |
| IF-05 | Assurance → action executor | `ActionRequest` | transition only | rejection is recorded and run fails safe |
| IF-06 | Runtime → evidence | snapshot/decision records | each tick/transition | append failure makes evidence incomplete |
| IF-07 | Evidence API → Open MCT | HTTP + WebSocket | live/history | explicit unavailable indicator |

The one-command demo defaults to loopback port 8765 for the API and 8766 for Open MCT,
with explicit `-ApiPort` and `-WebPort` overrides. It refuses occupied ports, propagates
the selected API origin into Vite, and accepts browser API access only from localhost
origins. Readiness is valid only when the API reports the requested run identifier. The
generic `lifeline serve` and `lifeline replay` CLI commands also retain configurable
ports.

Every critical field carries units, source time, receipt time, and validity. Simulation
time is authoritative for policy and replay; UTC receipt time is diagnostic only.
