# v1.1.0 release checklist

## Engineering qualification

- [x] The Python suite passes with at least 70% total coverage.
- [x] All 15 controlled scenarios retain their declared expectations.
- [x] Sanitized PX4 evidence exists for smoke, nominal T-01, and corrected T-05.
- [x] T-01 ends `RECOVERED` with delivery `ACCEPTED` and `ON_TIME`.
- [x] T-05 ends `SAFE_STOP`, rejects `RETURN`, records the controlled-land acknowledgement, and preserves `AIRCRAFT` custody.
- [x] Display qualification passes 27/27 with 12 hash-checked screenshots.
- [x] Four qualified-replay capture checks pass.
- [x] Schema drift, Ruff, PowerShell parsing, frontend tests, production build, and dependency audits pass.
- [x] Current-checkout and fresh-archive audits report `release_ready: true`.
- [ ] GitHub Actions is green for the exact release commit.

## Evidence and boundaries

- [x] Every retained evidence artifact is present and hash-complete.
- [x] Public PX4 derivatives retain source provenance and pass the content screen.
- [x] The project distinguishes MAVSDK vehicle telemetry from scripted assurance inputs.
- [x] Public wording stays within the simulation evidence.
- [x] The release archive excludes superseded evidence and private source logs.

## Release artifacts

- [x] Run `python scripts/verify_release_export.py` from the release commit.
- [x] Run `python scripts/build_release_package.py`.
- [x] Verify `dist/lifeline-evidence-v1.1.0.zip` against `dist/SHA256SUMS` and test its ZIP CRC.
- [ ] Tag `v1.1.0` only after hosted checks pass.

The exact private PX4 sources and the historical unhashed development bundles remain in checksummed archives outside the public repository.
