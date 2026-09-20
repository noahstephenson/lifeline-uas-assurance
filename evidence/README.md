# Evidence

Generated runs are stored under `evidence/runs/<run-id>/` and ignored by Git. A run is
complete only when every manifest-listed export exists, matches its recorded SHA-256,
and every controlled assertion passes. Missing, modified, and legacy-unchecked exports
produce an effective `INCOMPLETE` result.

`evidence/runs/REFERENCE-T05/` is the single committed, synthetic replay fixture. It
contains no real coordinates, operational data, patient data, or personal filesystem
paths and must remain identified as fake-source evidence.

Aggregate campaign reports are written under `evidence/campaigns/<campaign-id>/` and
are ignored by Git. They reference the individual run bundles and never replace them.
