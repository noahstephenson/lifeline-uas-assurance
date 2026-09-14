from __future__ import annotations

import csv
import json
import platform
import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

import yaml

from lifeline import __version__
from lifeline.config import PROJECT_ROOT, file_sha256
from lifeline.models import EvidenceManifest, VerificationState
from lifeline.scenarios.loader import scenario_path
from lifeline.scenarios.runner import ScenarioRun

RUNS_DIR = PROJECT_ROOT / "evidence" / "runs"


def export_run(run: ScenarioRun, output_root: Path | None = None) -> EvidenceManifest:
    root = output_root or RUNS_DIR
    run_dir = root / run.run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    scenario_file = scenario_path(run.scenario.id)
    config_file = PROJECT_ROOT / "config" / "baseline.yaml"
    passed = all(result.passed for result in run.assertions)
    status = VerificationState.PASS if passed else VerificationState.FAIL

    files = {
        "summary": "run-summary.json",
        "snapshots": "events.jsonl",
        "decisions": "decisions.jsonl",
        "assertions": "assertions.csv",
        "verification_matrix": "verification-matrix.csv",
        "environment": "environment.json",
        "scenario": "scenario-resolved.yaml",
        "timeline": "timeline.csv",
        "manifest": "manifest.json",
    }
    _write_jsonl(run_dir / files["snapshots"], run.snapshots)
    _write_jsonl(run_dir / files["decisions"], run.decisions)
    _write_assertions(run_dir / files["assertions"], run.assertions)
    _write_verification_matrix(run_dir / files["verification_matrix"], run)
    _write_timeline(run_dir / files["timeline"], run)
    (run_dir / files["scenario"]).write_text(yaml.safe_dump(run.scenario.model_dump(mode="json"), sort_keys=False), encoding="utf-8")
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
    }
    _write_json(run_dir / files["environment"], environment)
    summary = {
        "run_id": run.run_id,
        "scenario_id": run.scenario.id,
        "scenario_name": run.scenario.name,
        "verification_status": status.value,
        "terminal_state": run.snapshots[-1].mission_state.value,
        "snapshot_count": len(run.snapshots),
        "decision_count": len(run.decisions),
        "exploratory": run.snapshots[0].exploratory,
    }
    _write_json(run_dir / files["summary"], summary)
    manifest = EvidenceManifest(
        run_id=run.run_id,
        scenario_id=run.scenario.id,
        exploratory=run.snapshots[0].exploratory,
        verification_status=status,
        scenario_sha256=file_sha256(scenario_file),
        configuration_sha256=file_sha256(config_file),
        software_versions=environment,
        files=files,
        assertions=run.assertions,
    )
    _write_json(run_dir / files["manifest"], manifest.model_dump(mode="json"))
    return manifest


def list_runs(output_root: Path | None = None) -> list[dict[str, Any]]:
    root = output_root or RUNS_DIR
    if not root.exists():
        return []
    runs = []
    for path in sorted(root.glob("*/manifest.json"), reverse=True):
        runs.append(json.loads(path.read_text(encoding="utf-8")))
    return runs


def load_run(run_id: str, output_root: Path | None = None) -> dict[str, Any]:
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
