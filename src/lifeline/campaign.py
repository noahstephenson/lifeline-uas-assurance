from __future__ import annotations

import csv
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from lifeline.config import PROJECT_ROOT, load_config
from lifeline.evidence import export_run, list_runs, validate_evidence_id, verify_run_integrity
from lifeline.scenarios import load_scenarios, run_scenario
from lifeline.validation import _read_csv, _split

CAMPAIGNS_DIR = PROJECT_ROOT / "evidence" / "campaigns"


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
    px4_evidence = [
        item
        for item in list_runs(runs_root)
        if item["scenario_id"] == "T-01" and item["verification_status"] == "PASS" and item["software_versions"].get("source") == "px4"
    ]
    checks = {
        "controlled_campaign_threshold": bool(campaign and campaign["release_threshold_met"]),
        "all_campaign_evidence_integrity": campaign_integrity,
        "px4_sitl_qualification": bool(px4_evidence) and not any(item["requirement_id"] == "M-01" for item in deferred),
        "human_display_review": not any(item["requirement_id"].startswith("OD-") for item in deferred),
    }
    return {
        "release_ready": all(checks.values()),
        "campaign_id": campaign["campaign_id"] if campaign else None,
        "qualifying_px4_runs": [item["run_id"] for item in px4_evidence],
        "checks": checks,
        "deferred_requirements": deferred,
        "note": "A false release_ready result preserves declared environment and human-review gates.",
    }


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
