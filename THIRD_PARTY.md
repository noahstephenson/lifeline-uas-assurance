# Third-party architecture and provenance

| Project | Pinned baseline | License | Lifeline use |
|---|---|---|---|
| PX4-Autopilot | v1.17.0, commit `d6f12ad` | BSD-3-Clause | External WSL2 SITL and Gazebo X500; not vendored or modified |
| MAVSDK-Python | 3.17.2 | BSD-3-Clause | Optional dependency; connection, telemetry, mission, and action APIs |
| NASA Open MCT | 4.1.0 | Apache-2.0 | npm dependency; object, composition, telemetry, and time APIs |
| Playwright | 1.55.1 | Apache-2.0 | Automated browser display qualification at two declared viewports |
| Chromium | 140.0.7339.186 | BSD-style | Browser binary installed by pinned Playwright for display qualification |
| NASA openmct-tutorial | completed branch, reviewed 2026-09-13 | Apache-2.0 | Architectural reference for historical and WebSocket providers |
| NASA openmct-demo | reviewed 2026-09-13 | Apache-2.0 | Display-composition reference only |

Lifeline uses public extension points and independently implemented adapters. Any future
source copied verbatim or closely adapted must retain its upstream notice at the file and
be added to this register with its exact commit.
