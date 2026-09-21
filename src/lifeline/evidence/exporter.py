from __future__ import annotations

import csv
import ipaddress
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
HOME_PATH_PATTERN = re.compile(r"/home/[A-Za-z0-9._-]+")
WINDOWS_USER_PATH_PATTERN = re.compile(r"[A-Za-z]:[/\\\\]Users[/\\\\][^/\\\\\s]+", re.IGNORECASE)
WSL_USER_PATH_PATTERN = re.compile(r"/mnt/[a-z]/Users/[^/\s]+", re.IGNORECASE)
COORDINATE_PATTERN = re.compile(r'(?i)\b(?:latitude|longitude|latitude_deg|longitude_deg|lat_deg|lon_deg)\b')
PROHIBITED_OPERATIONAL_PATTERN = re.compile(r"(?i)\b(?:patient|casualty|weapon|targeting|tactical)\b")
ENDPOINT_IP_PATTERN = re.compile(
    r'(?i)(?:\b(?:udp|udpin|udpout|tcp|http|https|ws|wss)://|["\']endpoint["\']\s*:\s*["\'])(?P<ip>(?:\d{1,3}\.){3}\d{1,3})'
)
TEXT_SUFFIXES = {".csv", ".json", ".jsonl", ".log", ".md", ".svg", ".txt", ".yaml", ".yml"}


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
    _write_text(run_dir / files["scenario"], yaml.safe_dump(run.scenario.model_dump(mode="json"), sort_keys=False))
    _write_text(run_dir / files["configuration"], yaml.safe_dump(resolved_config.model_dump(mode="json"), sort_keys=False))
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
    _normalize_text_files(run_dir, files.values())
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
    _normalize_text_file(destination)
    manifest_path = run_dir / "manifest.json"
    manifest = loaded["manifest"]
    manifest.setdefault("files", {})[logical_name] = allowed[logical_name]
    manifest.setdefault("artifact_sha256", {})[logical_name] = file_sha256(destination)
    _write_json(manifest_path, manifest)
    return verify_run_integrity(run_id, output_root)


def export_public_run(run_id: str, staging_root: Path, output_root: Path | None = None) -> dict[str, Any]:
    """Create and verify a sanitized, provenance-linked derivative evidence bundle."""
    validate_evidence_id(run_id, label="run ID")
    loaded = load_run(run_id, output_root)
    source_dir = Path(loaded["directory"])
    source_integrity = verify_run_integrity(run_id, output_root)
    if not source_integrity["complete"]:
        raise ValueError(f"source evidence is incomplete: {run_id}")
    source_manifest_path = source_dir / "manifest.json"
    source_manifest_sha256 = file_sha256(source_manifest_path)

    staging_root = staging_root.resolve()
    staging_root.mkdir(parents=True, exist_ok=True)
    destination = (staging_root / run_id).resolve()
    if staging_root not in destination.parents:
        raise ValueError("public export destination escapes the staging root")
    if destination.exists():
        raise FileExistsError(f"public export already exists: {destination}")
    shutil.copytree(source_dir, destination)

    original_hashes = {
        path.relative_to(destination).as_posix(): file_sha256(path)
        for path in sorted(destination.rglob("*"))
        if path.is_file() and path.name != "manifest.json"
    }
    redactions: list[dict[str, Any]] = []
    for path in sorted(item for item in destination.rglob("*") if item.is_file() and _is_text_artifact(item)):
        text = path.read_text(encoding="utf-8", errors="strict")
        sanitized, count = HOME_PATH_PATTERN.subn("/home/<user>", text)
        if count:
            _write_text(path, sanitized)
            redactions.append(
                {
                    "artifact": path.relative_to(destination).as_posix(),
                    "rule": "linux-home-directory",
                    "replacement": "/home/<user>",
                    "count": count,
                }
            )
        else:
            _normalize_text_file(path)

    findings = _scan_public_bundle(destination)
    if findings:
        shutil.rmtree(destination)
        raise ValueError("public evidence policy rejected export: " + "; ".join(findings))

    manifest_path = destination / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    public_hashes = {
        path.relative_to(destination).as_posix(): file_sha256(path)
        for path in sorted(destination.rglob("*"))
        if path.is_file() and path.name not in {"manifest.json", "public-export.json"}
    }
    provenance = {
        "schema_version": "1.0.0",
        "export_type": "sanitized-public-export",
        "source_run_id": run_id,
        "source_manifest_sha256": source_manifest_sha256,
        "created_at": datetime_now(),
        "redaction_count": sum(item["count"] for item in redactions),
        "redactions": redactions,
        "original_artifact_sha256": original_hashes,
        "public_artifact_sha256": public_hashes,
    }
    _write_json(destination / "public-export.json", provenance)
    manifest.setdefault("files", {})["public_export"] = "public-export.json"
    manifest.setdefault("software_versions", {})["evidence_variant"] = "sanitized-public-export"
    manifest["software_versions"]["source_manifest_sha256"] = source_manifest_sha256
    manifest["artifact_sha256"] = {
        logical_name: file_sha256(destination / filename)
        for logical_name, filename in manifest["files"].items()
        if logical_name != "manifest" and (destination / filename).is_file()
    }
    _write_json(manifest_path, manifest)
    integrity = verify_run_integrity(run_id, staging_root)
    if not integrity["complete"]:
        shutil.rmtree(destination)
        raise ValueError(f"sanitized public evidence failed integrity verification: {integrity}")
    return {"run_id": run_id, "directory": str(destination), "integrity": integrity, "provenance": provenance}


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
    _write_text(path, json.dumps(value, indent=2, sort_keys=True) + "\n")


def _write_text(path: Path, value: str) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write(value)


def _write_jsonl(path: Path, values: list[Any]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        for value in values:
            stream.write(json.dumps(value.model_dump(mode="json"), sort_keys=True) + "\n")


def _write_assertions(path: Path, assertions: list) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        writer = csv.DictWriter(stream, fieldnames=["name", "passed", "expected", "observed"], lineterminator="\n")
        writer.writeheader()
        for assertion in assertions:
            writer.writerow(assertion.model_dump())


def _write_verification_matrix(path: Path, run: ScenarioRun) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=["requirement_id", "scenario_id", "status", "run_id"],
            lineterminator="\n",
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
    with path.open("w", encoding="utf-8", newline="\n") as stream:
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
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
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


def _is_text_artifact(path: Path) -> bool:
    return path.suffix.lower() in TEXT_SUFFIXES


def _normalize_text_file(path: Path) -> None:
    if not _is_text_artifact(path):
        return
    data = path.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    path.write_bytes(data)


def _normalize_text_files(root: Path, filenames: Any) -> None:
    for filename in filenames:
        path = root / filename
        if path.is_file():
            _normalize_text_file(path)


def _scan_public_bundle(root: Path) -> list[str]:
    findings: list[str] = []
    for path in sorted(item for item in root.rglob("*") if item.is_file() and _is_text_artifact(item)):
        relative = path.relative_to(root).as_posix()
        text = path.read_text(encoding="utf-8", errors="strict")
        if WINDOWS_USER_PATH_PATTERN.search(text) or WSL_USER_PATH_PATTERN.search(text):
            findings.append(f"{relative}: local user path")
        if HOME_PATH_PATTERN.search(text):
            findings.append(f"{relative}: unredacted Linux home path")
        if COORDINATE_PATTERN.search(text):
            findings.append(f"{relative}: geographic coordinate field")
        if PROHIBITED_OPERATIONAL_PATTERN.search(text):
            findings.append(f"{relative}: prohibited operational term")
        for match in ENDPOINT_IP_PATTERN.finditer(text):
            candidate = match.group("ip")
            try:
                address = ipaddress.ip_address(candidate)
            except ValueError:
                continue
            if not address.is_loopback:
                findings.append(f"{relative}: non-loopback endpoint {address}")
    return sorted(set(findings))
