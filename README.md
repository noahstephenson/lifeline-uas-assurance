# Project Lifeline

Project Lifeline is an educational, simulation-only mission-assurance workbench for a
fictional medical-resupply UAS. It connects deterministic contingency logic, scenario
injection, requirement-linked evidence, a live API, Open MCT telemetry, and optional PX4
software-in-the-loop (SITL).

> Project Lifeline is an independent educational simulation using fictional mission data.
> It is not an Army system, is not endorsed by the U.S. Army, does not model a fielded
> operational capability, and is not intended to support real flight or medical decisions.

## Quick start: deterministic simulation

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python -m pip install -e ".[dev]"
.\.venv\Scripts\lifeline --json doctor
.\.venv\Scripts\lifeline validate
.\.venv\Scripts\lifeline run --scenario T-05
.\.venv\Scripts\lifeline serve
```

For the visible dashboard, use the convenience launcher below and open
<http://127.0.0.1:8766/>. Evidence is written to `evidence/runs/<run-id>/`.
`lifeline serve` alone exposes the JSON API; it is not the visual console.

The convenience launcher is:

```powershell
.\scripts\demo.ps1 -Scenario T-05 -Mode Fake
```

If either default loopback port is occupied, choose another local pair:

```powershell
.\scripts\demo.ps1 -Scenario T-05 -Mode Replay -ApiPort 8875 -WebPort 8876
```

Use `-Mode Replay` for the committed, synthetic `REFERENCE-T05` bundle. If that bundle
is intentionally removed, the launcher generates a deterministic local reference run.

Live qualification uses a dedicated Ubuntu 24.04 WSL2 environment so PX4, MAVSDK,
Lifeline Python, and the API share true loopback. The Windows host runs only the
read-only Open MCT browser surface. Set up and qualify the pinned environment with:

```powershell
.\scripts\setup-px4-wsl.ps1
# Complete Ubuntu's first-launch local-account prompt, then rerun setup as directed.
.\scripts\qualify-px4.ps1 -Scenario Smoke
.\scripts\qualify-px4.ps1 -Scenario T-01
.\scripts\qualify-px4.ps1 -Scenario T-05
```

The setup script also installs a checksum-verified, project-local Node 20.20.2 runtime;
it does not replace the host's global Node installation.

`config/baseline.yaml` remains fail-closed. The qualification profile may differ from it
only by `actions_enabled: true`, and the code independently enforces the loopback endpoint,
explicit launcher token, nonzero vehicle UUID, and dashboard-before-release interlock.

## Command contract

All commands accept the global `--json` flag before the subcommand. In JSON mode stdout
contains exactly one JSON object. Success uses `{"ok": true, "data": ...}`; failure uses
`{"ok": false, "error": {"type": ..., "message": ...}}` and a nonzero exit code.

```text
lifeline --json doctor
lifeline validate
lifeline run --scenario T-01 [--source fake|px4]
lifeline live --scenario T-01 --config config/sitl-qualification.yaml
lifeline px4-smoke --config config/sitl-qualification.yaml
lifeline campaign run
lifeline campaign audit
lifeline runs list
lifeline runs show <run-id>
lifeline evidence --run <run-id>
lifeline figure --run <run-id>
lifeline replay --run <run-id>
lifeline serve [--host 127.0.0.1] [--port 8000]
lifeline inject --field navigation_confidence --value 0.25 --exploratory
```

`campaign run` executes the twelve controlled fake-source scenarios and writes an
aggregate summary plus requirement-coverage table under `evidence/campaigns/`.
`campaign audit` rechecks every referenced evidence checksum and reports separate PX4,
automated-display, discrepancy, and clean-worktree gates. Automated browser qualification
is not a human usability study.

## Safety boundary

- The Open MCT/browser surface is read-only.
- PX4 actions default to disabled and accept only a loopback SITL endpoint.
- No real coordinates, radio parameters, patient data, tactics, or fielded-system claims
  belong in this repository.
- Manual injection is exploratory and cannot satisfy controlled verification coverage.

See `docs/` for the CONOPS, architecture, interfaces, decision policy, hazards, and
verification plan.
