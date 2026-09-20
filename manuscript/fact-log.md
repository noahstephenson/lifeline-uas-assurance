# Manuscript fact log

| Draft statement | Classification | Evidence | Approved wording |
|---|---|---|---|
| The pure engine covers the controlled policy partitions | demonstrated | Automated suite; assurance-engine coverage report | Retain with the test scope, not as a general safety claim |
| The fake-source campaign produces requirement-linked evidence | demonstrated | `CAMPAIGN-20260920-B`; 12/12 PASS; all run integrity checks complete | “All twelve deterministic scenarios passed their frozen assertions.” |
| T-05 rejected return after navigation became invalid | demonstrated | `REFERENCE-T05`; return absent; `NAVIGATION_INVALID`; terminal `SAFE_STOP`; artifact hashes complete | Retain and identify it as modeled behavior |
| Open MCT serves current and historical assurance data | demonstrated for replay | Production build, frontend stale/loss tests, and 8875/8876 smoke selecting `REFERENCE-T05` | Use “replay console”; do not call it PX4-live |
| PX4 and Gazebo completed the campaign | proposed | none | Do not claim until WSL2 integration evidence exists |
| The design improves safety | unsupported/general | none | Replace with “makes modeled assumptions testable” |
| Visual layout passed human usability review | future | browser automation unavailable; no reviewer record | Do not claim |
