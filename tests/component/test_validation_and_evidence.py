import pytest

from lifeline.campaign import audit_release, run_fake_campaign
from lifeline.config import load_config
from lifeline.evidence import export_run, load_run, verify_run_integrity
from lifeline.scenarios import load_scenario, run_scenario
from lifeline.validation import validate_project


def test_project_traceability_is_valid():
    result = validate_project()
    assert result["valid"], result["errors"]
    assert result["counts"]["scenarios"] == 12


def test_evidence_bundle_contains_required_files(tmp_path, monkeypatch):
    run = run_scenario(load_scenario("T-05"), load_config(), run_id="TEST-EVIDENCE")
    manifest = export_run(run, tmp_path)
    run_dir = tmp_path / run.run_id
    assert manifest.verification_status.value == "PASS"
    assert all((run_dir / name).exists() for name in manifest.files.values())
    assert manifest.software_versions["openmct"] == "4.1.0"
    assert manifest.software_versions["source"] == "fake"
    assert verify_run_integrity(run.run_id, tmp_path)["verification_status"] == "PASS"


def test_modified_evidence_is_incomplete(tmp_path):
    run = run_scenario(load_scenario("T-05"), load_config(), run_id="TEST-CORRUPT")
    export_run(run, tmp_path)
    (tmp_path / run.run_id / "events.jsonl").write_text("{}\n", encoding="utf-8")
    integrity = verify_run_integrity(run.run_id, tmp_path)
    assert integrity["verification_status"] == "INCOMPLETE"
    assert integrity["mismatched"] == ["events.jsonl"]


def test_evidence_ids_cannot_escape_the_runs_directory(tmp_path):
    run = run_scenario(load_scenario("T-01"), load_config(), run_id="../ESCAPE")
    with pytest.raises(ValueError, match="run ID"):
        export_run(run, tmp_path)
    with pytest.raises(ValueError, match="run ID"):
        load_run("../ESCAPE", tmp_path)
    with pytest.raises(ValueError, match="campaign ID"):
        run_fake_campaign(
            campaign_id="../ESCAPE",
            runs_root=tmp_path / "runs",
            campaigns_root=tmp_path / "campaigns",
        )


def test_controlled_campaign_aggregates_all_scenarios(tmp_path):
    campaigns_root = tmp_path / "campaigns"
    result = run_fake_campaign(
        campaign_id="TEST-CAMPAIGN",
        runs_root=tmp_path / "runs",
        campaigns_root=campaigns_root,
    )
    assert result["scenario_total"] == 12
    assert result["scenario_passed"] == 12
    assert result["release_threshold_met"]
    audit = audit_release("TEST-CAMPAIGN", campaigns_root, tmp_path / "runs")
    assert audit["checks"]["controlled_campaign_threshold"]
    assert audit["checks"]["all_campaign_evidence_integrity"]
    assert audit["checks"]["automated_display_qualification"]
    assert not audit["release_ready"]
    assert {item["requirement_id"] for item in audit["deferred_requirements"]} == {"M-01"}
