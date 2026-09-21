# Claim-evidence register

| Claim | Current status | Evidence and allowed wording |
|---|---|---|
| Defined response for every modeled scenario | demonstrated with fake source | Final T-01–T-12 campaign: 12/12 PASS. “The implemented model produced defined responses for the documented scenario set.” |
| Every contingency transition includes trigger and requirement | demonstrated | Schema-valid `decisions.jsonl` records and T-05 inspection. “Each recorded transition included its trigger and applicable requirement.” |
| Console supports current and historical assurance telemetry | demonstrated in simulation | Open MCT production build, automated browser display qualification, frontend service-loss tests, T-12 replay, and dashboard/PX4 overlap in `LFL-T01-PX4-20260921T094403Z-1CE3` and `LFL-T05-PX4-20260921T095622Z-00F1`. No human usability study was performed. |
| Testing exposed useful integration issues | demonstrated | D-01 through D-15 cover readiness, provenance, artifact integrity, configurable ports, timing, framework startup, cross-shell setup, venv/path finalization, bounded SITL launch failures, background WSL argument boundaries, the pinned MAVSDK identity contract, persistent live telemetry, fail-closed qualification status, and the CLI audit envelope. Do not imply these were flight-safety findings. |
| The display presents the declared evidence fields and explicit failure states | demonstrated by automation | `evidence/display-qualification/display-qualification.json`, eight screenshots, and DISPLAY-T01/T05/T11/T12. Say “automated browser display qualification,” not “human usability validated.” |
| PX4/Gazebo completed controlled simulation missions | demonstrated in SITL | Stock-X500 smoke `LFL-SMOKE-PX4-20260921T022921Z-A837`, nominal T-01 `LFL-T01-PX4-20260921T094403Z-1CE3`, and compound-fault T-05 `LFL-T05-PX4-20260921T095622Z-00F1` are hash-complete `PASS` bundles. Say “PX4 software-in-the-loop,” never real flight or operational validation. |
