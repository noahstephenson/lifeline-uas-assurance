# Evidence

The current branch contains the final v1.1 qualification set:

- the 15 runs in `CAMPAIGN-20260922-PRESENTATION-V11`;
- six synthetic display fixtures for T-01, corrected T-05, T-11, T-13, T-14, and T-15;
- 12 screenshots referenced by the automated display report;
- sanitized PX4 evidence for smoke, nominal T-01, and corrected T-05;
- four screenshots captured from the qualified PX4 replays.

Earlier campaigns, fixtures, and PX4 runs remain available in Git history. They are not included in the current release archive.

Generated runs are written to `evidence/runs/<run-id>/` and are ignored unless `.gitignore` names them as release evidence. A run is complete only when every file listed by its manifest exists, matches its SHA-256 value, and passes every controlled assertion. Missing, modified, or unchecked files produce an effective `INCOMPLETE` result.

The PX4 bundles are sanitized public derivatives. Each contains `public-export.json`, links back to the privately preserved source-manifest hash, replaces the local Linux username, and passes the public-content screen. Local ignored runs cannot satisfy the tracked PX4 release gate.

All coordinates, requests, package data, and deadlines are fictional. Public evidence must not contain patient information, personal filesystem paths, non-loopback endpoints, or operational data.

`python scripts/verify_release_export.py` creates a fresh `git archive` of `HEAD` and runs the same strict evidence audit from the exported tree.
