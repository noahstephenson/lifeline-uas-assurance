from __future__ import annotations

import csv
import json
import platform
import re
import shutil
import subprocess
import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

import yaml

from lifeline import __version__
from lifeline.config import PROJECT_ROOT, file_sha256, load_config
from lifeline.figures import render_timeline_svg
from lifeline.models import EvidenceManifest, VerificationState
from lifeline.scenarios.loader import scenario_path
from lifeline.scenarios.runner import ScenarioRun

RUNS_DIR = PROJECT_ROOT / "evidence" / "runs"
EVIDENCE_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


def validate_evidence_id(value: str, *, label: str = "evidence ID") -> str:
    if not EVIDENCE_ID_PATTERN.fullmatch(value):
        raise ValueError(f"{label} must contain only letters, digits, dot, underscore, or hyphen")
    return value


def reserve_evidence_directory(run_id: str, output_root: Path | None = None) -> Path:
    """Create the run directory before external connection work begins."""
    validate_evidence_id(run_id, label="run ID")
    run_dir = (output_root or RUNS_DIR) / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    (run_dir / ".reserved").write_text(datetime_now(), encoding="utf-8")
    return run_dir


def export_run(run: ScenarioRun, output_root: Path | None = None) -> EvidenceManifest:
    root = output_root or RUNS_DIR
    validate_evidence_id(run.run_id, label="run ID")
    run_dir = root / run.run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    if (run_dir / "manifest.json").exists():
        raise FileExistsError(f"evidence run already finalized: {run.run_id}")
    unexpected = [item.name for item in run_dir.iterdir() if item.name != ".reserved"]
    if unexpected:
        raise FileExistsError(f"evidence run directory is not empty: {run.run_id}")
    (run_dir / ".reserved").unlink(missing_ok=True)
    scenario_file = scenario_path(run.scenario.id)
    resolved_config = run.configuration or load_config()
    passed = all(result.passed for result in run.assertions)
    status = VerificationState.ERROR if run.error else VerificationState.PASS if passed else VerificationState.FAIL

    files = {
        "summary": "run-summary.json",
        "snapshots": "events.jsonl",
        "decisions": "decisions.jsonl",
        "commands": "commands.jsonl",
        "assertions": "assertions.csv",
        "verification_matrix": "verification-matrix.csv",
        "environment": "environment.json",
        "scenario": "scenario-resolved.yaml",
        "configuration": "configuration-resolved.yaml",
        "timeline": "timeline.csv",
        "timeline_svg": "timeline.svg",
        "manifest": "manifest.json",
    }
    if run.source == "px4":
        files.update({"px4_log": "px4.log", "api_log": "api.log"})
    _write_jsonl(run_dir / files["snapshots"], run.snapshots)
    _write_jsonl(run_dir / files["decisions"], run.decisions)
    _write_jsonl(run_dir / files["commands"], run.commands)
    _write_assertions(run_dir / files["assertions"], run.assertions)
    _write_verification_matrix(run_dir / files["verification_matrix"], run)
    _write_timeline(run_dir / files["timeline"], run)
    render_timeline_svg(run_dir, run.run_id)
    (run_dir / files["scenario"]).write_text(yaml.safe_dump(run.scenario.model_dump(mode="json"), sort_keys=False), encoding="utf-8")
    (run_dir / files["configuration"]).write_text(
        yaml.safe_dump(resolved_config.model_dump(mode="json"), sort_keys=False),
        encoding="utf-8",
    )
    environment = {
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "lifeline": __version__,
        "source": run.source,
        "fastapi": _distribution_version("fastapi"),
        "mavsdk": _distribution_version("mavsdk"),
        "openmct": _openmct_version(),
        "pydantic": _distribution_version("pydantic"),
        "pyyaml": _distribution_version("pyyaml"),
        "uvicorn": _distribution_version("uvicorn"),
        **(collect_px4_environment() if run.source == "px4" else {}),
        **run.environment,
    }
    _write_json(run_dir / files["environment"], environment)
    summary = {
        "run_id": run.run_id,
        "scenario_id": run.scenario.id,
        "scenario_name": run.scenario.name,
        "verification_status": status.value,
        "terminal_state": run.snapshots[-1].mission_state.value if run.snapshots else "UNAVAILABLE",
        "snapshot_count": len(run.snapshots),
        "decision_count": len(run.decisions),
        "exploratory": run.snapshots[0].exploratory if run.snapshots else False,
        "error": run.error,
    }
    _write_json(run_dir / files["summary"], summary)
    artifact_sha256 = {
        logical_name: file_sha256(run_dir / filename)
        for logical_name, filename in files.items()
        if logical_name != "manifest" and (run_dir / filename).exists()
    }
    manifest = EvidenceManifest(
        run_id=run.run_id,
        scenario_id=run.scenario.id,
        exploratory=run.snapshots[0].exploratory if run.snapshots else False,
        verification_status=status,
        scenario_sha256=file_sha256(scenario_file),
        configuration_sha256=file_sha256(run_dir / files["configuration"]),
        software_versions=environment,
        files=files,
        artifact_sha256=artifact_sha256,
        assertions=run.assertions,
    )
    _write_json(run_dir / files["manifest"], manifest.model_dump(mode="json"))
    return manifest


def attach_run_artifact(
    run_id: str,
    logical_name: str,
    source: Path,
    output_root: Path | None = None,
) -> dict[str, Any]:
    allowed = {"px4_log": "px4.log", "api_log": "api.log"}
    if logical_name not in allowed:
        raise ValueError(f"unsupported attached artifact: {logical_name}")
    loaded = load_run(run_id, output_root)
    run_dir = Path(loaded["directory"])
    source = source.resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    destination = run_dir / allowed[logical_name]
    shutil.copyfile(source, destination)
    manifest_path = run_dir / "manifest.json"
    manifest = loaded["manifest"]
    manifest.setdefault("files", {})[logical_name] = allowed[logical_name]
    manifest.setdefault("artifact_sha256", {})[logical_name] = file_sha256(destination)
    _write_json(manifest_path, manifest)
    return verify_run_integrity(run_id, output_root)


def verify_run_integrity(run_id: str, output_root: Path | None = None) -> dict[str, Any]:
    loaded = load_run(run_id, output_root)
    run_dir = Path(loaded["directory"])
    manifest = loaded["manifest"]
    missing = sorted(filename for filename in manifest["files"].values() if not (run_dir / filename).exists())
    expected_hashes = manifest.get("artifact_sha256", {})
    mismatched: list[str] = []
    unchecked: list[str] = []
    for logical_name, filename in manifest["files"].items():
        if logical_name == "manifest" or filename in missing:
            continue
        expected = expected_hashes.get(logical_name)
        if not expected:
            unchecked.append(filename)
        elif file_sha256(run_dir / filename) != expected:
            mismatched.append(filename)
    return {
        "run_id": run_id,
        "complete": not missing and not mismatched and not unchecked,
        "missing": missing,
        "mismatched": sorted(mismatched),
        "unchecked": sorted(unchecked),
        "verification_status": ("INCOMPLETE" if missing or mismatched or unchecked else manifest["verification_status"]),
    }


def list_runs(output_root: Path | None = None) -> list[dict[str, Any]]:
    root = output_root or RUNS_DIR
    if not root.exists():
        return []
    runs = []
    for path in sorted(root.glob("*/manifest.json"), reverse=True):
        runs.append(json.loads(path.read_text(encoding="utf-8")))
    return runs


def load_run(run_id: str, output_root: Path | None = None) -> dict[str, Any]:
    validate_evidence_id(run_id, label="run ID")
    root = output_root or RUNS_DIR
    run_dir = (root / run_id).resolve()
    if root.resolve() not in run_dir.parents:
        raise ValueError("invalid run id")
    manifest_path = run_dir / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"run not found: {run_id}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    return {"directory": str(run_dir), "manifest": manifest}


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, values: list[Any]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        for value in values:
            stream.write(json.dumps(value.model_dump(mode="json"), sort_keys=True) + "\n")


def _write_assertions(path: Path, assertions: list) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=["name", "passed", "expected", "observed"])
        writer.writeheader()
        for assertion in assertions:
            writer.writerow(assertion.model_dump())


def _write_verification_matrix(path: Path, run: ScenarioRun) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=["requirement_id", "scenario_id", "status", "run_id"],
        )
        writer.writeheader()
        status = "pass" if all(item.passed for item in run.assertions) else "fail"
        for requirement in run.scenario.trace.requirements:
            writer.writerow(
                {
                    "requirement_id": requirement,
                    "scenario_id": run.scenario.id,
                    "status": status,
                    "run_id": run.run_id,
                }
            )


def _write_timeline(path: Path, run: ScenarioRun) -> None:
    decisions = {item.sequence: item for item in run.decisions}
    with path.open("w", encoding="utf-8", newline="") as stream:
        fields = [
            "sim_time_s",
            "mission_state",
            "assurance_state",
            "action",
            "link",
            "navigation_confidence",
            "energy_margin_wh",
            "decision_code",
        ]
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        active_state = "NOMINAL"
        active_action = "NONE"
        active_code = "NOMINAL"
        for snapshot in run.snapshots:
            if snapshot.sequence in decisions:
                record = decisions[snapshot.sequence]
                active_state = record.new_state.value
                active_action = record.recommended_action.value
                active_code = record.decision_code
            writer.writerow(
                {
                    "sim_time_s": snapshot.sim_time_s,
                    "mission_state": snapshot.mission_state.value,
                    "assurance_state": active_state,
                    "action": active_action,
                    "link": snapshot.operator_link_available.value,
                    "navigation_confidence": snapshot.navigation_confidence.value,
                    "energy_margin_wh": snapshot.energy_margin_wh.value,
                    "decision_code": active_code,
                }
            )


def _distribution_version(name: str) -> str:
    try:
        return version(name)
    except PackageNotFoundError:
        return "not-installed"


def _openmct_version() -> str:
    package_lock = PROJECT_ROOT / "openmct" / "package-lock.json"
    if not package_lock.exists():
        return "not-installed"
    data = json.loads(package_lock.read_text(encoding="utf-8"))
    return data.get("packages", {}).get("node_modules/openmct", {}).get("version", "unknown")


def datetime_now() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).isoformat()


def collect_px4_environment() -> dict[str, str]:
    return {
        "wsl_kernel": platform.release(),
        "ubuntu_release": _ubuntu_release(),
        "px4_tag": _command_version(["git", "-C", str(Path.home() / "PX4-Autopilot"), "describe", "--tags", "--exact-match"]),
        "px4_commit": _command_version(["git", "-C", str(Path.home() / "PX4-Autopilot"), "rev-parse", "HEAD"]),
        "gazebo_version": _command_version(["gz", "sim", "--version"]),
    }


def _ubuntu_release() -> str:
    path = Path("/etc/os-release")
    if not path.exists():
        return "not-wsl"
    values = dict(line.split("=", 1) for line in path.read_text(encoding="utf-8").splitlines() if "=" in line)
    return values.get("VERSION_ID", "unknown").strip('"')


def _command_version(command: list[str]) -> str:
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=10, check=False)
        value = (result.stdout or result.stderr).strip().splitlines()
        return value[0] if result.returncode == 0 and value else "unavailable"
    except (OSError, subprocess.SubprocessError):
        return "unavailable"
