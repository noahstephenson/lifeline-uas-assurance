import json

import pytest

from lifeline.campaign import audit_release, run_fake_campaign
from lifeline.config import load_config
from lifeline.evidence import attach_run_artifact, export_public_run, export_run, load_run, verify_run_integrity
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


def test_public_export_redacts_home_and_preserves_source(tmp_path):
    source_root = tmp_path / "source"
    public_root = tmp_path / "public"
    run = run_scenario(load_scenario("T-01"), load_config(), run_id="TEST-PUBLIC")
    export_run(run, source_root)
    source_log = tmp_path / "px4-source.log"
    source_log.write_text("built from /home/student/PX4-Autopilot on 127.0.0.1\n", encoding="utf-8")
    attach_run_artifact(run.run_id, "px4_log", source_log, source_root)
    source_manifest_before = (source_root / run.run_id / "manifest.json").read_bytes()

    result = export_public_run(run.run_id, public_root, source_root)

    assert result["integrity"]["complete"]
    assert (source_root / run.run_id / "manifest.json").read_bytes() == source_manifest_before
    assert "/home/<user>" in (public_root / run.run_id / "px4.log").read_text(encoding="utf-8")
    assert "/home/student" not in (public_root / run.run_id / "px4.log").read_text(encoding="utf-8")
    manifest = load_run(run.run_id, public_root)["manifest"]
    provenance = result["provenance"]
    assert manifest["software_versions"]["evidence_variant"] == "sanitized-public-export"
    assert manifest["software_versions"]["source_manifest_sha256"] == provenance["source_manifest_sha256"]
    assert provenance["redaction_count"] == 1


@pytest.mark.parametrize(
    "unsafe_text, expected",
    [
        ("uplink udpin://192.168.1.40:14540\n", "non-loopback endpoint"),
        ('{"latitude_deg": 38.0}\n', "geographic coordinate field"),
    ],
)
def test_public_export_rejects_operational_data(tmp_path, unsafe_text, expected):
    source_root = tmp_path / "source"
    run = run_scenario(load_scenario("T-01"), load_config(), run_id="TEST-REJECT")
    export_run(run, source_root)
    source_log = tmp_path / "px4-source.log"
    source_log.write_text(unsafe_text, encoding="utf-8")
    attach_run_artifact(run.run_id, "px4_log", source_log, source_root)
    with pytest.raises(ValueError, match=expected):
        export_public_run(run.run_id, tmp_path / "public", source_root)


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
    assert audit["deferred_requirements"] == []
    assert not audit["checks"]["px4_sitl_qualification"]


def test_untracked_evidence_cannot_satisfy_px4_gate(tmp_path):
    runs_root = tmp_path / "runs"
    run = run_scenario(load_scenario("T-01"), load_config(), run_id="LOCAL-ONLY-PX4")
    export_run(run, runs_root)
    manifest_path = runs_root / run.run_id / "manifest.json"
    manifest = load_run(run.run_id, runs_root)["manifest"]
    manifest["software_versions"].update(
        {
            "source": "px4",
            "evidence_variant": "sanitized-public-export",
            "dashboard_px4_time_overlap": "true",
            "vehicle_uuid": "1234",
        }
    )
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    audit = audit_release(runs_root=runs_root)

    assert audit["qualifying_px4_runs"] == []
    assert not audit["checks"]["tracked_px4_evidence"]
