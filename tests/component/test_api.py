import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

from lifeline.api import create_app
from lifeline.config import load_config
from lifeline.evidence import export_run, exporter
from lifeline.scenarios import load_scenario, run_scenario


def test_history_and_current_state(tmp_path, monkeypatch):
    monkeypatch.setattr(exporter, "RUNS_DIR", tmp_path)
    import lifeline.api.app as api_app

    monkeypatch.setattr(api_app, "RUNS_DIR", tmp_path)
    run = run_scenario(load_scenario("T-01"), load_config(), run_id="TEST-API")
    export_run(run, tmp_path)
    client = TestClient(create_app("TEST-API"))
    assert client.get("/api/v1/health").status_code == 200
    state = client.get("/api/v1/state").json()
    assert state["mission_state"] == "RECOVERED"
    history = client.get("/api/v1/history", params={"key": "energy_margin_wh"}).json()
    assert history and history[0]["id"] == "energy_margin_wh"


def test_missing_required_export_is_reported_incomplete(tmp_path, monkeypatch):
    monkeypatch.setattr(exporter, "RUNS_DIR", tmp_path)
    import lifeline.api.app as api_app

    monkeypatch.setattr(api_app, "RUNS_DIR", tmp_path)
    run = run_scenario(load_scenario("T-05"), load_config(), run_id="TEST-INCOMPLETE")
    export_run(run, tmp_path)
    (tmp_path / run.run_id / "events.jsonl").unlink()

    response = TestClient(create_app(run.run_id)).get(f"/api/v1/runs/{run.run_id}/verification")
    assert response.status_code == 200
    verification = response.json()
    assert verification["verification_status"] == "INCOMPLETE"
    assert verification["missing_files"] == ["events.jsonl"]
