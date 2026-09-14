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

`Live` mode additionally requires Ubuntu 24.04 WSL2, PX4 v1.17, Gazebo Harmonic, and the
`px4` optional dependency. The command path is locked to localhost SITL. Actions require
both `-AllowSitlActions` at launch and `sitl.actions_enabled: true` in the controlled
configuration.

## Command contract

All commands accept the global `--json` flag before the subcommand. In JSON mode stdout
contains exactly one JSON object. Success uses `{"ok": true, "data": ...}`; failure uses
`{"ok": false, "error": {"type": ..., "message": ...}}` and a nonzero exit code.

```text
lifeline --json doctor
lifeline validate
lifeline run --scenario T-01 [--source fake|px4]
lifeline runs list
lifeline runs show <run-id>
lifeline evidence --run <run-id>
lifeline figure --run <run-id>
lifeline replay --run <run-id>
lifeline serve [--host 127.0.0.1] [--port 8000]
lifeline inject --field navigation_confidence --value 0.25 --exploratory
```

## Safety boundary

- The Open MCT/browser surface is read-only.
- PX4 actions default to disabled and accept only a loopback SITL endpoint.
- No real coordinates, radio parameters, patient data, tactics, or fielded-system claims
  belong in this repository.
- Manual injection is exploratory and cannot satisfy controlled verification coverage.

See `docs/` for the CONOPS, architecture, interfaces, decision policy, hazards, and
verification plan.
