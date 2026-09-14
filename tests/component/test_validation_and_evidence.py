from lifeline.config import load_config
from lifeline.evidence import export_run
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
