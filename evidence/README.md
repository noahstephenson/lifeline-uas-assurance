# Evidence

Generated runs are stored under `evidence/runs/<run-id>/` and ignored by Git. A run is
complete only when every manifest-listed export exists and every controlled assertion
passes.

`evidence/runs/REFERENCE-T05/` is the single committed, synthetic replay fixture. It
contains no real coordinates, operational data, patient data, or personal filesystem
paths and must remain identified as fake-source evidence.
