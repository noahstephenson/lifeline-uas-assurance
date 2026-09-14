# Manuscript fact log

| Draft statement | Classification | Evidence | Approved wording |
|---|---|---|---|
| The pure engine covers the controlled policy partitions | demonstrated | 27-test suite; assurance engine 99% line coverage | Retain with the test scope, not as a general safety claim |
| The fake-source campaign produces requirement-linked evidence | demonstrated | Final T-01–T-12 bundles; 12/12 PASS | “All twelve deterministic scenarios passed their frozen assertions.” |
| T-05 rejected return after navigation became invalid | demonstrated | `LFL-T05-20260914T124546Z`; return absent; `NAVIGATION_INVALID`; terminal `SAFE_STOP` | Retain and identify it as modeled behavior |
| Open MCT serves current and historical assurance data | demonstrated for replay | Production build, dedicated-port HTTP smoke, launcher-selected T-12 replay | Use “replay console”; do not call it PX4-live |
| PX4 and Gazebo completed the campaign | proposed | none | Do not claim until WSL2 integration evidence exists |
| The design improves safety | unsupported/general | none | Replace with “makes modeled assumptions testable” |
| Visual layout passed human usability review | future | browser automation unavailable; no reviewer record | Do not claim |
