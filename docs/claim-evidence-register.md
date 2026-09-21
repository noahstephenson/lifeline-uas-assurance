# Claim-evidence register

| Claim | Current status | Evidence and allowed wording |
|---|---|---|
| Defined response for every modeled scenario | demonstrated with fake source | Final T-01–T-12 campaign: 12/12 PASS. “The implemented model produced defined responses for the documented scenario set.” |
| Every contingency transition includes trigger and requirement | demonstrated | Schema-valid `decisions.jsonl` records and T-05 inspection. “Each recorded transition included its trigger and applicable requirement.” |
| Console supports current and historical assurance telemetry | partially demonstrated | Open MCT production build, frontend service-loss tests, loopback HTTP smoke test, and T-12 replay launcher pass. Human display review and live PX4-to-console operation remain deferred. |
| Testing exposed useful integration issues | demonstrated | D-01 through D-07 cover readiness, source provenance, artifact integrity, configurable ports, timing allowance, framework startup, and launcher parsing. Do not imply these were flight-safety findings. |
| The display presents the declared evidence fields and explicit failure states | demonstrated by automation | `evidence/display-qualification/display-qualification.json`, eight screenshots, and DISPLAY-T01/T05/T11/T12. Say “automated browser display qualification,” not “human usability validated.” |
| PX4/Gazebo completed a controlled mission | not demonstrated | No evidence. Do not claim until an environment-qualified SITL bundle exists. |
