# Contributing

Keep changes small enough to review and tie them to the existing engineering records.

A change to assurance behavior must update the decision policy, requirements, hazards, traceability, affected scenarios, and tests in the same commit. Do not change an expected scenario result simply to make a test pass. Record a discrepancy first and preserve the failed controlled run.

Use fictional data and loopback endpoints. The Open MCT application must remain read-only, and SITL actions must continue to require explicit opt-in.

Before review, run:

    lifeline validate
    pytest
    ruff check .
