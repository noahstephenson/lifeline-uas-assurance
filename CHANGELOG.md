# Changelog

## v1.1.0

### Added

- A versioned request, package, receiving-station, and receipt model.
- Independent aircraft, delivery, and timeliness outcomes.
- Scenarios T-13 through T-15 for missing, mismatched, and late receipts.
- A telemetry-driven mission map, custody display, coordinated timeline, presentation mode, and time-local explanations.
- PX4 qualification of the full T-01 handoff and return workflow.
- Four qualified-replay screenshots for the project walkthrough.

### Changed

- T-05 now preserves package custody with the aircraft after an off-origin contingency landing.
- The final controlled campaign contains 15 scenarios.
- Browser display qualification now contains 27 assertions and 12 screenshots.
- Release verification and packaging use the final v1.1 campaign and PX4 evidence.

## v1.0.0

### Added

- A deterministic assurance engine and 12 controlled scenarios.
- Requirements, hazards, interfaces, traceability, discrepancy records, and claim-evidence records.
- A replayable FastAPI and WebSocket evidence service.
- A read-only Open MCT dashboard.
- PX4 v1.17.0 and Gazebo X500 smoke, nominal, and contingency evidence.
- Sanitized public evidence export and fresh-archive verification.

## Release boundary

Project Lifeline is a simulation-only student project. The evidence does not establish real-flight performance, human usability, operational safety, certification, medical suitability, or endorsement.

## Known build warnings

- Open MCT's upstream legacy CSS produces compatibility warnings during minification.
- Vite reports the expected Open MCT bundle-size warning.
