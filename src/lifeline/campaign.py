from __future__ import annotations

import csv
import hashlib
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from lifeline.config import PROJECT_ROOT, load_config
from lifeline.evidence import export_run, list_runs, validate_evidence_id, verify_run_integrity
from lifeline.scenarios import load_scenarios, run_scenario
from lifeline.validation import _read_csv, _split

CAMPAIGNS_DIR = PROJECT_ROOT / "evidence" / "campaigns"
DISPLAY_REPORT = PROJECT_ROOT / "evidence" / "display-qualification" / "display-qualification.json"


def run_fake_campaign(
    *,
    campaign_id: str | None = None,
    runs_root: Path | None = None,
    campaigns_root: Path | None = None,
) -> dict[str, Any]:
    campaign_id = campaign_id or f"CAMPAIGN-{datetime.now(UTC):%Y%m%dT%H%M%SZ}"
    validate_evidence_id(campaign_id, label="campaign ID")
    campaigns_root = campaigns_root or CAMPAIGNS_DIR
    if campaign_id:
        validate_evidence_id(campaign_id, label="campaign ID")
    campaign_dir = campaigns_root / campaign_id
    campaign_dir.mkdir(parents=True, exist_ok=False)
    config = load_config()
    results: list[dict[str, Any]] = []
    for scenario in load_scenarios():
        run = run_scenario(
            scenario,
            config,
            run_id=f"{campaign_id}-{scenario.id.replace('-', '')}",
        )
        export_run(run, runs_root)
        integrity = verify_run_integrity(run.run_id, runs_root)
        results.append(
            {
                "scenario_id": scenario.id,
                "run_id": run.run_id,
                "verification_status": integrity["verification_status"],
                "assertions_passed": sum(item.passed for item in run.assertions),
                "assertions_total": len(run.assertions),
                "integrity_complete": integrity["complete"],
            }
        )

    passed = sum(item["verification_status"] == "PASS" for item in results)
    summary = {
        "campaign_id": campaign_id,
        "source": "fake",
        "controlled": True,
        "created_at": datetime.now(UTC).isoformat(),
        "scenario_total": len(results),
        "scenario_passed": passed,
        "scenario_failed": len(results) - passed,
        "release_threshold": 10,
        "release_threshold_met": passed >= 10 and len(results) == 12,
        "results": results,
    }
    (campaign_dir / "campaign-summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    _write_requirement_coverage(campaign_dir / "requirement-coverage.csv", results)
    return {**summary, "directory": str(campaign_dir)}


def audit_release(
    campaign_id: str | None = None,
    campaigns_root: Path | None = None,
    runs_root: Path | None = None,
) -> dict[str, Any]:
    campaigns_root = campaigns_root or CAMPAIGNS_DIR
    summaries = sorted(campaigns_root.glob("*/campaign-summary.json"), reverse=True)
    if campaign_id:
        summary_path = campaigns_root / campaign_id / "campaign-summary.json"
    elif summaries:
        summary_path = summaries[0]
    else:
        summary_path = None
    campaign = json.loads(summary_path.read_text(encoding="utf-8")) if summary_path and summary_path.exists() else None
    trace_rows = _read_csv(PROJECT_ROOT / "requirements" / "traceability.csv")
    deferred = [
        {"requirement_id": row["requirement_id"], "status": row["status"]} for row in trace_rows if row["status"].startswith("deferred")
    ]
    campaign_integrity = False
    if campaign:
        try:
            campaign_integrity = all(verify_run_integrity(item["run_id"], runs_root)["complete"] for item in campaign["results"])
        except (FileNotFoundError, ValueError):
            campaign_integrity = False
    all_runs = list_runs(runs_root)
    px4_evidence = [
        item
        for item in all_runs
        if item.get("scenario_id") in {"T-01", "T-05"}
        and item.get("verification_status") == "PASS"
        and item.get("software_versions", {}).get("source") == "px4"
        and verify_run_integrity(item["run_id"], runs_root)["complete"]
        and item.get("software_versions", {}).get("dashboard_px4_time_overlap") == "true"
        and item.get("software_versions", {}).get("vehicle_uuid") not in {None, "0", 0}
    ]
    px4_scenarios = {item["scenario_id"] for item in px4_evidence}
    smoke_evidence = [
        item
        for item in all_runs
        if item.get("kind") == "px4-smoke"
        and item.get("verification_status") == "PASS"
        and verify_run_integrity(item["run_id"], runs_root)["complete"]
    ]
    display = _audit_display_qualification()
    checks = {
        "controlled_campaign_threshold": bool(campaign and campaign["release_threshold_met"]),
        "all_campaign_evidence_integrity": campaign_integrity,
        "px4_sitl_qualification": px4_scenarios == {"T-01", "T-05"}
        and bool(smoke_evidence)
        and not any(item["requirement_id"] == "M-01" for item in deferred),
        "automated_display_qualification": display["passed"],
        "no_unexplained_discrepancy": "**Status:** open-unexplained"
        not in (PROJECT_ROOT / "docs" / "discrepancies.md").read_text(encoding="utf-8"),
        "clean_git_working_tree": _git_clean(),
    }
    return {
        "release_ready": all(checks.values()),
        "campaign_id": campaign["campaign_id"] if campaign else None,
        "qualifying_px4_runs": [item["run_id"] for item in px4_evidence],
        "qualifying_px4_smoke_runs": [item["run_id"] for item in smoke_evidence],
        "display_qualification": display,
        "checks": checks,
        "deferred_requirements": deferred,
        "note": (
            "A false release_ready result preserves declared environment, integrity, PX4, "
            "automated-display, discrepancy, and repository gates."
        ),
    }


def _audit_display_qualification() -> dict[str, Any]:
    if not DISPLAY_REPORT.exists():
        return {"passed": False, "reason": "display qualification report is missing"}
    try:
        report = json.loads(DISPLAY_REPORT.read_text(encoding="utf-8"))
        assertions = report.get("assertions", [])
        screenshots = report.get("screenshots", {})
        expected_runs = {"DISPLAY-T01", "DISPLAY-T05", "DISPLAY-T11", "DISPLAY-T12"}
        hashes_match = all(
            (DISPLAY_REPORT.parent / name).is_file() and _sha256(DISPLAY_REPORT.parent / name) == digest
            for name, digest in screenshots.items()
        )
        fixtures_match = all(
            verify_run_integrity(run_id)["complete"]
            and report.get("fixtures", {}).get(run_id) == _directory_hash(PROJECT_ROOT / "evidence" / "runs" / run_id)
            for run_id in expected_runs
        )
        passed = (
            report.get("verification_status") == "PASS"
            and report.get("qualification_method") == "automated browser display qualification"
            and report.get("human_usability_study") is False
            and len(assertions) == 15
            and all(item.get("passed") for item in assertions)
            and len(screenshots) == 8
            and hashes_match
            and set(report.get("fixtures", {})) == expected_runs
            and fixtures_match
        )
        return {
            "passed": passed,
            "report": str(DISPLAY_REPORT),
            "assertions": len(assertions),
            "screenshots": len(screenshots),
            "hashes_match": hashes_match,
            "fixtures_match": fixtures_match,
        }
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        return {"passed": False, "reason": f"invalid display qualification report: {exc}"}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _directory_hash(directory: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(item for item in directory.rglob("*") if item.is_file()):
        digest.update(path.relative_to(directory).as_posix().encode())
        digest.update(_sha256(path).encode())
    return digest.hexdigest()


def _git_clean() -> bool:
    result = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0 and not result.stdout.strip()


def _write_requirement_coverage(path: Path, results: list[dict[str, Any]]) -> None:
    result_by_scenario = {item["scenario_id"]: item for item in results}
    trace_rows = _read_csv(PROJECT_ROOT / "requirements" / "traceability.csv")
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=["requirement_id", "declared_status", "scenario_ids", "scenario_evidence_status"],
        )
        writer.writeheader()
        for row in trace_rows:
            scenario_ids = _split(row.get("test_ids", ""))
            mapped = [result_by_scenario[item] for item in scenario_ids if item in result_by_scenario]
            if row["status"].startswith("deferred"):
                evidence_status = "deferred"
            elif not mapped:
                evidence_status = "no-scenario-mapping"
            elif all(item["verification_status"] == "PASS" for item in mapped):
                evidence_status = "scenario-evidence-pass"
            else:
                evidence_status = "scenario-evidence-fail"
            writer.writerow(
                {
                    "requirement_id": row["requirement_id"],
                    "declared_status": row["status"],
                    "scenario_ids": ";".join(scenario_ids),
                    "scenario_evidence_status": evidence_status,
                }
            )
