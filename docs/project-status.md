# Project status

Project Lifeline v1.1 is implemented as a Medical Resupply Mission Lab. Its evidence
status is intentionally split between the preserved v1.0 qualification baseline and new
v1.1 behavior awaiting refreshed campaign evidence.

## Implemented v1.1 capabilities

- A versioned mission contract identifies the fictional request, package, origin,
  recipient, delivery zone, landed handoff, acceptance rules, and logistics deadline.
- The receiving-station simulator records custody and validates request, package, and
  recipient identifiers before accepting a receipt.
- Aircraft, delivery, and timeliness outcomes are independent.
- Fifteen scenarios include nominal receipt, receiver absence, wrong-package rejection,
  and accepted-but-late delivery.
- Evidence includes delivery events, the resolved mission contract, and a deterministic
  after-action summary.
- The dashboard provides a telemetry-driven local-NED map, request/manifest view,
  coordinated timeline, outcome strip, replay controls, and Explain this moment.
- `scripts/mission.ps1` provides an interactive catalogue plus direct Synthetic, Replay,
  and explicitly authorized SITL modes.
- The PX4 integration now lands at the receiving station before modeled unload/receipt,
  then explicitly rearms, takes off, and returns.

## Qualification status

- The immutable v1.0 campaign, browser evidence, and PX4 runs remain the historical
  baseline for the behavior they recorded.
- The controlled `CAMPAIGN-20260921-MEDICAL-V11` campaign passed 15/15 scenarios with
  complete bundle integrity.
- Automated v1.1 display qualification passed 21/21 checks and generated 12 new desktop
  and compact screenshots while retaining the historical screenshots.
- A new T-01/T-05 SITL campaign is required before the landing-handoff-return integration
  is called PX4-qualified. Old aircraft evidence is not reused for that claim.

## Sensible next extensions

- Add randomized receiver delay and network-jitter experiments as exploratory runs.
- Add a characterized alternate recovery location and only then consider `DIVERT`.
- Run a separately designed human-factors study; automated display checks are not one.
- Apply the fictional payload mass to a characterized vehicle-dynamics model.
- Add hardware-in-the-loop as a separate evidence class without weakening SITL controls.

All results remain limited to the documented simulation configuration. They do not
establish real-flight performance, operational safety, certification, medical suitability,
or military capability.
