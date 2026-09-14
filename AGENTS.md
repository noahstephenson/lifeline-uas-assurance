# Project Lifeline agent rules

- Preserve the simulation-only boundary. Never add real hardware endpoints or operational data.
- Keep `lifeline.assurance` independent of PX4, FastAPI, Open MCT, and filesystem adapters.
- Update requirements, hazards, scenarios, and traceability together when behavior changes.
- Do not relabel an expected result to make a scenario pass; record a discrepancy first.
- Generated evidence cannot be called passed if an assertion or required export is missing.
- Open MCT is read-only. SITL actions require explicit loopback allowlisting and opt-in.
- Do not claim safety validation, Army endorsement, real-flight performance, or certification.

