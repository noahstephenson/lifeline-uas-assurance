# Evidence

Generated runs are stored under `evidence/runs/<run-id>/` and ignored by Git unless an
explicit release-fixture exception is declared in `.gitignore`. A run is
complete only when every manifest-listed export exists, matches its recorded SHA-256,
and every controlled assertion passes. Missing, modified, and legacy-unchecked exports
produce an effective `INCOMPLETE` result.

Committed evidence consists of the controlled twelve-run campaign, four display
fixtures, `REFERENCE-T05`, and three sanitized public PX4 derivatives. The PX4
derivatives include `public-export.json`, link to a privately preserved source-manifest
hash, replace local Linux home names, and pass the public-content screen. A local ignored
run can never satisfy the tracked-PX4 release gate.

The replay and display fixtures are synthetic fake-source evidence. No public bundle may
contain real coordinates, non-loopback endpoints, patient data, operational data, or
personal filesystem paths.

Aggregate campaign reports are written under `evidence/campaigns/<campaign-id>/` and
are ignored by Git. They reference the individual run bundles and never replace them.

`python scripts/verify_release_export.py --allow-incomplete-metadata` creates and audits a
fresh `git archive` of `HEAD`. Omit the flag for the strict tagged-release gate.
