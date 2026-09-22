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
    assert state["verification_status"] == "PASS"
    assert state["evidence_complete"] is True
    assert state["delivery_outcome"] == "ACCEPTED"
    assert state["timeliness"] == "ON_TIME"
    assert state["receipt_status"] == "ACCEPTED"
    history = client.get("/api/v1/history", params={"key": "energy_margin_wh"}).json()
    assert history and history[0]["id"] == "energy_margin_wh"
    full_history = client.get("/api/v1/history").json()
    assert "verification_status" not in full_history[0]
    assert full_history[-1]["verification_status"] == "PASS"
    assert full_history[-1]["evidence_complete"] is True
    cors = client.get(
        "/api/v1/health",
        headers={"Origin": "http://127.0.0.1:8876"},
    )
    assert cors.headers["access-control-allow-origin"] == "http://127.0.0.1:8876"
    contract = client.get("/api/v1/mission-contract").json()
    assert contract["request_id"] == state["request_id"]
    assert contract["package"]["cold_chain_required"] is False
    scenarios = client.get("/api/v1/scenarios").json()
    assert any(item["id"] == "T-15" for item in scenarios)
    runs = client.get("/api/v1/runs", params={"scenario_id": "T-01"}).json()
    assert runs[0]["delivery_outcome"] == "ACCEPTED"
    events = client.get("/api/v1/runs/TEST-API/delivery-events").json()
    assert any(item["event_type"] == "RECEIPT_ACCEPTED" for item in events)
    after_action = client.get("/api/v1/runs/TEST-API/after-action").json()
    assert after_action["outcomes"] == {
        "aircraft": "RECOVERED",
        "delivery": "ACCEPTED",
        "timeliness": "ON_TIME",
        "receipt": "ACCEPTED",
    }


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


def test_modified_required_export_is_reported_incomplete(tmp_path, monkeypatch):
    monkeypatch.setattr(exporter, "RUNS_DIR", tmp_path)
    import lifeline.api.app as api_app

    monkeypatch.setattr(api_app, "RUNS_DIR", tmp_path)
    run = run_scenario(load_scenario("T-05"), load_config(), run_id="TEST-TAMPERED")
    export_run(run, tmp_path)
    (tmp_path / run.run_id / "events.jsonl").write_text("{}\n", encoding="utf-8")

    verification = TestClient(create_app(run.run_id)).get(f"/api/v1/runs/{run.run_id}/verification").json()
    assert verification["verification_status"] == "INCOMPLETE"
    assert verification["mismatched_files"] == ["events.jsonl"]


def test_replay_stream_finishes_with_explicit_status(tmp_path, monkeypatch):
    monkeypatch.setattr(exporter, "RUNS_DIR", tmp_path)
    import lifeline.api.app as api_app

    monkeypatch.setattr(api_app, "RUNS_DIR", tmp_path)
    run = run_scenario(load_scenario("T-05"), load_config(), run_id="TEST-STREAM")
    export_run(run, tmp_path)
    with TestClient(create_app(run.run_id)).websocket_connect("/api/v1/stream") as socket:
        messages = [socket.receive_json() for _ in range(len(run.snapshots) + 1)]
    status = messages[-1]
    assert status["message_type"] == "status"
    assert status["status"] == "replay_complete"
    assert status["payload"] == {"status": "replay_complete"}
    assert status["run_id"] == "TEST-STREAM"
    assert status["sequence"] == run.snapshots[-1].sequence
    assert messages[-2]["payload"]["mission_state"] == "SAFE_STOP"
    assert messages[-2]["payload"]["evidence_complete"] is True

    resume_after = run.snapshots[-3].sequence
    with TestClient(create_app(run.run_id)).websocket_connect(
        f"/api/v1/stream?after_sequence={resume_after}&speed=16"
    ) as socket:
        resumed = [socket.receive_json() for _ in range(3)]
    assert resumed[0]["sequence"] == resume_after + 1
    assert resumed[-1]["status"] == "replay_complete"
