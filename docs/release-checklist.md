# v1.0.0-magazine-demo release checklist

## Automated qualification

- [x] Python suite passes with at least 70% total coverage.
- [x] Twelve controlled fake-source scenarios retain their declared expectations.
- [x] Sanitized public PX4 evidence exists for smoke, T-01, and T-05.
- [x] T-01 terminates `RECOVERED`.
- [x] T-05 terminates `SAFE_STOP`, rejects `RETURN`, and records controlled-land acknowledgement.
- [x] Display qualification passes 15/15 with eight hash-checked screenshots.
- [x] Schema generation, Ruff, PowerShell parsing, frontend tests, production build, and dependency audits pass.
- [ ] Strict current-checkout and fresh-archive release audits report `release_ready: true`.
- [ ] GitHub Actions is green for the exact release commit.

## Publication metadata

- [ ] Replace `Student Name` with the preferred publication name.
- [ ] Add advisor attribution supplied by the project owner.
- [ ] Replace `OWNER` with the exact GitHub owner/repository URL.
- [ ] Add a genuine project photograph outside the software evidence claim set.
- [ ] Set the citation release date when the tag is created.

## Publication package

- [ ] Confirm simulation-only wording and the absence of real-flight, human-usability,
  operational-safety, certification, or Army-endorsement claims.
- [ ] Confirm the manuscript distinguishes MAVSDK physical telemetry from scripted assurance-input faults.
- [ ] Create a curated public evidence ZIP from the three sanitized PX4 bundles and controlled fixtures.
- [ ] Generate `SHA256SUMS` for release attachments.
- [ ] Tag `v1.0.0-magazine-demo` from the tested clean commit and attach only public artifacts.

Private preservation completed on 2026-09-21: the exact original PX4 archive hashes to
`6f63fffec85e45c4c45aa4b772107d4bda70c89530fa89dc462d68e2ca0ffb1d`; the 48-bundle
historical unhashed-development archive hashes to
`d9e82db8bdfdef856cfeeacd4d7db80664d6027a3930f2e0fd5cd46ec5fcd541`.

After metadata is complete, `python scripts/build_release_package.py` creates the exact
curated ZIP and checksum file used by the strict release workflow. During local release
preparation, `--allow-incomplete-metadata` permits a package dry run while leaving the
strict audit false.
