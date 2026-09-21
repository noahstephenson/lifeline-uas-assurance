from __future__ import annotations

import asyncio
import json
import os
import platform
from collections.abc import Awaitable
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from time import monotonic
from typing import Any

import yaml

from lifeline.config import LifelineConfig, file_sha256
from lifeline.evidence.exporter import RUNS_DIR, collect_px4_environment, validate_evidence_id
from lifeline.models import CommandName, CommandRecord
from lifeline.telemetry import MavsdkAdapter


async def run_px4_smoke(
    config: LifelineConfig,
    *,
    run_id: str,
    output_root: Path | None = None,
    adapter_factory: type[MavsdkAdapter] = MavsdkAdapter,
    connect_timeout_s: float = 30.0,
) -> dict[str, Any]:
    """Exercise stock SITL and always leave a hash-verifiable smoke bundle."""
    validate_evidence_id(run_id, label="run ID")
    root = output_root or RUNS_DIR
    run_dir = root / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    config_path = run_dir / "configuration-resolved.yaml"
    config_path.write_text(yaml.safe_dump(config.model_dump(mode="json"), sort_keys=False), encoding="utf-8")
    commands: list[CommandRecord] = []
    observations: list[dict[str, Any]] = []
    started = monotonic()
    adapter: MavsdkAdapter | None = None
    status = "ERROR"
    error: str | None = None

    async def issue(name: CommandName, operation: Awaitable[str]) -> None:
        requested = round(monotonic() - started, 3)
        try:
            acknowledgement = await operation
            commands.append(
                CommandRecord(
                    sequence=len(commands),
                    command=name,
                    requested_at_s=requested,
                    accepted=True,
                    acknowledgement=acknowledgement,
                    completed_at_s=round(monotonic() - started, 3),
                    observed_completion_state="ACTION_ACKNOWLEDGED",
                )
            )
        except Exception as exc:
            commands.append(
                CommandRecord(
                    sequence=len(commands),
                    command=name,
                    requested_at_s=requested,
                    accepted=False,
                    acknowledgement="rejected",
                    error=f"{type(exc).__name__}: {exc}",
                )
            )
            raise

    try:
        adapter = adapter_factory(config, allow_sitl_actions=True)
        await asyncio.wait_for(adapter.connect(), timeout=connect_timeout_s)
        await adapter.wait_ready()
        await issue(CommandName.ARM, adapter.arm())
        await issue(CommandName.TAKEOFF, adapter.takeoff(8.0))
        peak_altitude = await _observe_takeoff(adapter, observations)
        if peak_altitude <= 5.0:
            raise RuntimeError(f"vehicle did not exceed 5 m; observed {peak_altitude:.2f} m")
        _complete_command(commands, CommandName.TAKEOFF, monotonic() - started, "ALTITUDE_ABOVE_5_M")
        await issue(CommandName.LAND, adapter.land())
        await _observe_landing(adapter, observations)
        _complete_command(commands, CommandName.LAND, monotonic() - started, "IN_AIR_FALSE")
        status = "PASS"
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
    return _finalize_smoke(run_dir, run_id, config, adapter, commands, observations, status, error)


def finalize_smoke_setup_error(
    config: LifelineConfig,
    *,
    run_id: str,
    error: str,
    output_root: Path | None = None,
) -> dict[str, Any]:
    """Finalize a launch/setup failure before the MAVSDK adapter can connect."""
    validate_evidence_id(run_id, label="run ID")
    root = output_root or RUNS_DIR
    run_dir = root / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    if (run_dir / "manifest.json").exists():
        raise FileExistsError(f"smoke evidence already finalized: {run_id}")
    config_path = run_dir / "configuration-resolved.yaml"
    if not config_path.exists():
        config_path.write_text(yaml.safe_dump(config.model_dump(mode="json"), sort_keys=False), encoding="utf-8")
    return _finalize_smoke(run_dir, run_id, config, None, [], [], "ERROR", error)


async def _observe_takeoff(adapter: MavsdkAdapter, observations: list[dict[str, Any]], timeout_s: float = 45.0) -> float:
    deadline = monotonic() + timeout_s
    peak = 0.0
    while monotonic() < deadline:
        sample = await adapter.sample()
        in_air = await adapter.in_air()
        peak = max(peak, sample.relative_altitude_m)
        observations.append({"recorded_at": datetime.now(UTC).isoformat(), "altitude_m": sample.relative_altitude_m, "in_air": in_air})
        if in_air and sample.relative_altitude_m > 5.0:
            return peak
        await asyncio.sleep(0.5)
    return peak


async def _observe_landing(adapter: MavsdkAdapter, observations: list[dict[str, Any]], timeout_s: float = 45.0) -> None:
    deadline = monotonic() + timeout_s
    while monotonic() < deadline:
        sample = await adapter.sample()
        in_air = await adapter.in_air()
        observations.append({"recorded_at": datetime.now(UTC).isoformat(), "altitude_m": sample.relative_altitude_m, "in_air": in_air})
        if not in_air:
            return
        await asyncio.sleep(0.5)
    raise TimeoutError("vehicle did not report in_air=false after land acknowledgement")


def _finalize_smoke(
    run_dir: Path,
    run_id: str,
    config: LifelineConfig,
    adapter: MavsdkAdapter | None,
    commands: list[CommandRecord],
    observations: list[dict[str, Any]],
    status: str,
    error: str | None,
) -> dict[str, Any]:
    files = {
        "commands": "commands.jsonl",
        "observations": "observations.jsonl",
        "environment": "environment.json",
        "configuration": "configuration-resolved.yaml",
        "summary": "smoke-summary.json",
        "px4_log": "px4.log",
        "manifest": "manifest.json",
    }
    _write_jsonl(run_dir / files["commands"], [item.model_dump(mode="json") for item in commands])
    _write_jsonl(run_dir / files["observations"], observations)
    environment = {
        "platform": platform.platform(),
        "python": platform.python_version(),
        "mavsdk": _version("mavsdk"),
        **collect_px4_environment(),
        "ubuntu_release_declared": os.getenv("LIFELINE_UBUNTU_RELEASE", "unreported"),
        "px4_tag_declared": os.getenv("LIFELINE_PX4_TAG", "unreported"),
        "px4_commit_declared": os.getenv("LIFELINE_PX4_COMMIT", "unreported"),
        "vehicle_uuid": str(adapter.vehicle_uuid if adapter else 0),
        "endpoint": config.sitl.endpoint,
        "telemetry_source": "mavsdk",
    }
    _write_json(run_dir / files["environment"], environment)
    summary = {
        "run_id": run_id,
        "kind": "px4-smoke",
        "verification_status": status,
        "error": error,
        "peak_altitude_m": max((item["altitude_m"] for item in observations), default=0.0),
        "landed": bool(observations and observations[-1]["in_air"] is False),
    }
    _write_json(run_dir / files["summary"], summary)
    hashes = {
        logical: file_sha256(run_dir / filename)
        for logical, filename in files.items()
        if logical != "manifest" and (run_dir / filename).exists()
    }
    manifest = {
        "schema_version": "1.0",
        "run_id": run_id,
        "scenario_id": "PX4-SMOKE",
        "kind": "px4-smoke",
        "verification_status": status,
        "configuration_sha256": file_sha256(run_dir / files["configuration"]),
        "files": files,
        "artifact_sha256": hashes,
        "environment": environment,
        "software_versions": {**environment, "source": "px4"},
        "error": error,
    }
    _write_json(run_dir / files["manifest"], manifest)
    return manifest


def _complete_command(commands: list[CommandRecord], name: CommandName, completed_at_s: float, state: str) -> None:
    index = next(index for index in range(len(commands) - 1, -1, -1) if commands[index].command == name)
    commands[index] = commands[index].model_copy(update={"completed_at_s": round(completed_at_s, 3), "observed_completion_state": state})


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, values: list[dict[str, Any]]) -> None:
    path.write_text("".join(json.dumps(value, sort_keys=True) + "\n" for value in values), encoding="utf-8")


def _version(name: str) -> str:
    try:
        return version(name)
    except PackageNotFoundError:
        return "not-installed"
