# Claim-evidence register

| Claim | Current status | Evidence and allowed wording |
|---|---|---|
| Defined response for every modeled scenario | demonstrated with fake source | Final T-01–T-12 campaign: 12/12 PASS. “The implemented model produced defined responses for the documented scenario set.” |
| Every contingency transition includes trigger and requirement | demonstrated | Schema-valid `decisions.jsonl` records and T-05 inspection. “Each recorded transition included its trigger and applicable requirement.” |
| Console supports current and historical assurance telemetry | partially demonstrated | Open MCT production build, loopback HTTP smoke test, and T-12 replay launcher pass. Live PX4-to-console operation remains deferred. |
| Testing exposed useful integration issues | demonstrated | D-01 dedicated-port correction and D-02 source-provenance/PX4 routing correction. Do not imply these were flight-safety findings. |
| PX4/Gazebo completed a controlled mission | not demonstrated | No evidence. Do not claim until an environment-qualified SITL bundle exists. |
