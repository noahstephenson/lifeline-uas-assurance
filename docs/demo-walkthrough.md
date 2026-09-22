# Medical Resupply Mission Lab demonstration

## Five-minute walkthrough

1. Run `.\scripts\mission.ps1 -Scenario T-01 -Mode Synthetic`.
2. In the outcome strip, point out that Aircraft, Delivery, and Timeliness are separate.
3. Follow the aircraft and package markers on the local-NED map. These are fictional
   coordinates, not an operational route.
4. At Echo Aid Station, observe arrival, landing, modeled unloading progress, custody
   transfer, and the matching receipt. Waypoint arrival alone does not complete delivery.
5. Pause replay, select a timeline transition, and use **Explain this moment** to inspect
   what the policy knew, what was unavailable, its allowed action, rejected alternatives,
   and requirement/hazard trace links.
6. Run T-14. The aircraft recovers, but the wrong-package receipt produces an independent
   `REJECTED` delivery outcome.
7. Open the evidence directory and inspect `after-action.json`, `delivery-events.jsonl`,
   `assertions.csv`, and `manifest.json`.

## Claims to make

- The deterministic model distinguishes flight completion from logistics completion.
- A receipt is accepted only when request, package, and recipient identifiers match.
- Recorded decisions and delivery events are traceable and replayable.
- The system demonstrates these properties in the documented simulation configuration.

## Claims not to make

- Do not describe the package, deadline, energy model, or receiving station as clinically
  validated.
- Do not imply real-flight testing, operational readiness, certified autonomy, or a human
  usability study.
