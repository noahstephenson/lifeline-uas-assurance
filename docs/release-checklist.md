# v1.0.0 release checklist

## Engineering qualification

- [x] Python suite passes with at least 70% total coverage.
- [x] Twelve controlled fake-source scenarios retain their declared expectations.
- [x] Sanitized public PX4 evidence exists for smoke, T-01, and T-05.
- [x] T-01 terminates `RECOVERED`.
- [x] T-05 terminates `SAFE_STOP`, rejects `RETURN`, and records the
  controlled-land acknowledgement.
- [x] Display qualification passes 15/15 with eight hash-checked screenshots.
- [x] Schema generation, Ruff, PowerShell parsing, frontend tests, production build,
  and dependency audits pass.
- [ ] Strict current-checkout and fresh-archive audits report `release_ready: true`
  for the release commit.
- [ ] GitHub Actions is green for the exact release commit.

## Evidence and boundaries

- [x] Every committed evidence artifact is present and hash-complete.
- [x] Public PX4 derivatives retain source provenance and pass the content screen.
- [x] The project distinguishes MAVSDK vehicle telemetry from scripted assurance-input
  faults.
- [x] Simulation-only wording excludes real-flight, human-usability,
  operational-safety, certification, and Army-endorsement claims.
- [x] The deterministic evidence archive excludes private source logs and historical
  unhashed development runs.

## Release artifacts

- [ ] Run `python scripts/verify_release_export.py` from the release commit.
- [ ] Run `python scripts/build_release_package.py`.
- [ ] Verify `dist/lifeline-evidence-v1.0.0.zip` against `dist/SHA256SUMS`.
- [ ] Tag `v1.0.0` only after the clean commit passes hosted checks.

Private preservation completed on 2026-09-21: the exact original PX4 archive hashes to
`6f63fffec85e45c4c45aa4b772107d4bda70c89530fa89dc462d68e2ca0ffb1d`; the 48-bundle
historical unhashed-development archive hashes to
`d9e82db8bdfdef856cfeeacd4d7db80664d6027a3930f2e0fd5cd46ec5fcd541`.
