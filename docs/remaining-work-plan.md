# Remaining build plan

This plan begins from the deterministic assurance, evidence API, Open MCT replay, and
guarded PX4 adapter baseline. A gate is closed only by its declared evidence.

## Tranche A — controlled evidence and console resilience

- Add aggregate T-01–T-12 campaign execution and requirement coverage.
- Hash every manifest-declared artifact and recheck it during API, CLI, and release audit.
- Expose evidence completeness in the console.
- Replace apparently healthy telemetry with explicit stale, disconnected, or unavailable
  states when the data service fails.
- Exercise those states with frontend unit tests.

Exit: Python, frontend, schema, deterministic campaign, and reference-replay checks pass.

## Tranche B — automated display qualification

- Launch T-01, T-05, T-11, and T-12 in the production Open MCT build.
- Run the pinned Playwright/Chromium suite at 1440×900 and 800×1000.
- Preserve T-01, T-05, T-11, and T-12 fixture hashes, screenshots, assertion results,
  browser version, and the machine-readable qualification report.
- Correct discrepancies without changing controlled expected outcomes.
- Mark OD-01 through OD-04 verified only after the automated report is hash-complete.

Exit: mission/assurance/health/evidence are legible together; state is distinguishable
without color; rationale and trace links are present; loss of data replaces the operational
view. These are browser assertions, not human-comprehension or usability findings.

## Tranche C — stock PX4/Gazebo qualification

- Use Ubuntu 24.04 WSL2, PX4 v1.17, Gazebo Harmonic, and the X500 model.
- Prove stock manual takeoff and landing before enabling Lifeline actions.
- Confirm the MAVSDK endpoint resolves only to the configured loopback address.
- Run T-01, then T-05, with both the launcher switch and controlled config opt-in.
- Preserve environment, action acknowledgements, logs, evidence hashes, and discrepancies.

Exit: M-01 has a complete PX4-source evidence bundle. A simulator window alone is not
evidence that PX4 supplied Lifeline telemetry.

## Tranche D — publication release

- Resolve or explicitly retain every discrepancy.
- Add student/advisor attribution and a genuine project photograph.
- Re-run the claim audit and remove every unsupported sentence.
- Tag `v1.0.0-magazine-demo` only from a clean commit with passing CI.

Exit: every result claim resolves to a complete bundle and the simulation-only disclaimer
is prominent.
