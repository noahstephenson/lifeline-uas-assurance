# Environment baseline

| Component | Baseline |
|---|---|
| Windows | Windows 11 host |
| Python | 3.11.x through 3.12.x (3.12 native in Ubuntu 24.04) |
| Node.js | 20.20.2 portable Windows archive for Open MCT |
| Ubuntu | 24.04 WSL2 |
| PX4 | v1.17.0, commit `d6f12ad` |
| Gazebo | PX4-supported Harmonic stack |
| MAVSDK-Python | 3.17.2 |
| Open MCT | 4.1.x |

Every run captures Python, platform, Lifeline, FastAPI, Pydantic, PyYAML, Uvicorn,
MAVSDK, Open MCT, and telemetry-source versions. `lifeline doctor` separately reports
tool availability and the controlled SITL endpoint. The verified local fake/replay run
used Python 3.11.0 and Open MCT 4.1.0. `scripts/setup-px4-wsl.ps1` downloads the pinned
official Node 20.20.2 Windows archive, verifies it against the release SHA-256 list, and
keeps it project-local without replacing the host's global Node installation.
