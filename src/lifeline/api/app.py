from __future__ import annotations

import asyncio
from typing import Any

from fastapi import FastAPI, HTTPException, Query, WebSocket
from fastapi.middleware.cors import CORSMiddleware

from lifeline.delivery import load_mission_contract
from lifeline.evidence.exporter import RUNS_DIR, list_runs, load_run, read_jsonl, verify_run_integrity
from lifeline.scenarios import load_scenario, load_scenarios

TELEMETRY_METADATA = [
    {"key": "mission_state", "name": "Mission state", "format": "string"},
    {"key": "assurance_state", "name": "Assurance state", "format": "string"},
    {"key": "recommended_action", "name": "Recommended action", "format": "string"},
    {"key": "operator_link_available", "name": "Operator link", "format": "boolean"},
    {
        "key": "navigation_confidence",
        "name": "Navigation confidence",
        "format": "number",
        "unit": "score",
    },
    {"key": "energy_margin_wh", "name": "Energy margin", "format": "number", "unit": "Wh"},
    {"key": "battery_remaining_pct", "name": "Battery remaining", "format": "number", "unit": "%"},
    {"key": "route_progress", "name": "Route progress", "format": "number", "unit": "fraction"},
    {"key": "relative_altitude_m", "name": "Relative altitude", "format": "number", "unit": "m"},
    {"key": "ground_speed_mps", "name": "Ground speed", "format": "number", "unit": "m/s"},
    {"key": "delivery_outcome", "name": "Delivery outcome", "format": "string"},
    {"key": "timeliness", "name": "Timeliness", "format": "string"},
    {"key": "package_custody", "name": "Package custody", "format": "string"},
    {"key": "receipt_status", "name": "Receipt status", "format": "string"},
    {"key": "deadline_remaining_s", "name": "Deadline remaining", "format": "number", "unit": "s"},
    {"key": "handoff_progress", "name": "Handoff progress", "format": "number", "unit": "fraction"},
]


def create_app(default_run_id: str | None = None) -> FastAPI:
    app = FastAPI(title="Project Lifeline Evidence API", version="1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=r"^http://(127\.0\.0\.1|localhost):\d{2,5}$",
        allow_methods=["GET"],
        allow_headers=["*"],
    )
    app.state.default_run_id = default_run_id

    @app.get("/api/v1/health")
    def health() -> dict[str, Any]:
        selected = _select_run(app.state.default_run_id)
        return {"status": "ok", "mode": "evidence", "selected_run": selected}

    @app.get("/api/v1/metadata")
    def metadata(run_id: str | None = None) -> dict[str, Any]:
        selected = _require_run(run_id or app.state.default_run_id)
        return {"schema_version": "1.0", "run_id": selected, "measurements": TELEMETRY_METADATA}

    @app.get("/api/v1/scenarios")
    def scenarios() -> list[dict[str, Any]]:
        return [
            {
                "id": item.id,
                "name": item.name,
                "duration_s": item.duration_s,
                "event_count": len(item.events),
                "expected_terminal_state": item.expect.terminal_state.value,
                "expected_delivery_outcome": (
                    item.expect.delivery_outcome.value if item.expect.delivery_outcome else "NOT_DECLARED"
                ),
            }
            for item in load_scenarios()
        ]

    @app.get("/api/v1/scenarios/{scenario_id}")
    def scenario_detail(scenario_id: str) -> dict[str, Any]:
        try:
            return load_scenario(scenario_id).model_dump(mode="json")
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/api/v1/mission-contract")
    def mission_contract() -> dict[str, Any]:
        return load_mission_contract().model_dump(mode="json")

    @app.get("/api/v1/runs")
    def runs(
        scenario_id: str | None = None,
        source: str | None = None,
        status: str | None = None,
        delivery_outcome: str | None = None,
    ) -> list[dict[str, Any]]:
        items = [_run_catalog_item(item) for item in list_runs()]
        if scenario_id:
            items = [item for item in items if item.get("scenario_id") == scenario_id]
        if source:
            items = [item for item in items if item.get("source") == source]
        if status:
            items = [item for item in items if item.get("verification_status") == status]
        if delivery_outcome:
            items = [item for item in items if item.get("delivery_outcome") == delivery_outcome]
        return items

    @app.get("/api/v1/runs/{run_id}")
    def run_detail(run_id: str) -> dict[str, Any]:
        try:
            return load_run(run_id)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/api/v1/state")
    def state(run_id: str | None = None) -> dict[str, Any]:
        selected = _require_run(run_id or app.state.default_run_id)
        snapshots = _read_run_file(selected, "events.jsonl")
        decisions = _read_run_file(selected, "decisions.jsonl")
        return _merge_snapshot(snapshots[-1], decisions, _verification_summary(selected))

    @app.get("/api/v1/history")
    def history(
        run_id: str | None = None,
        key: str | None = None,
        start: float = Query(default=0, ge=0),
        end: float | None = Query(default=None, ge=0),
    ) -> list[dict[str, Any]]:
        if end is not None and end < start:
            raise HTTPException(status_code=400, detail="end must be greater than or equal to start")
        selected = _require_run(run_id or app.state.default_run_id)
        snapshots = _read_run_file(selected, "events.jsonl")
        decisions = _read_run_file(selected, "decisions.jsonl")
        verification = _verification_summary(selected)
        final_sequence = snapshots[-1]["sequence"]
        points = [
            _merge_snapshot(item, decisions, verification if item["sequence"] == final_sequence else None)
            for item in snapshots
        ]
        points = [p for p in points if p["sim_time_s"] >= start and (end is None or p["sim_time_s"] <= end)]
        if key:
            valid = {item["key"] for item in TELEMETRY_METADATA}
            if key not in valid:
                raise HTTPException(status_code=404, detail=f"unknown telemetry key: {key}")
            return [{"timestamp": p["sim_time_s"] * 1000, "value": _value_for_key(p, key), "id": key} for p in points]
        return points

    @app.get("/api/v1/runs/{run_id}/decisions")
    def decisions(run_id: str) -> list[dict[str, Any]]:
        selected = _require_run(run_id)
        return _read_run_file(selected, "decisions.jsonl")

    @app.get("/api/v1/runs/{run_id}/delivery-events")
    def delivery_events(run_id: str) -> list[dict[str, Any]]:
        selected = _require_run(run_id)
        path = RUNS_DIR / selected / "delivery-events.jsonl"
        return read_jsonl(path) if path.exists() else []

    @app.get("/api/v1/runs/{run_id}/after-action")
    def after_action(run_id: str) -> dict[str, Any]:
        selected = _require_run(run_id)
        path = RUNS_DIR / selected / "after-action.json"
        if not path.exists():
            raise HTTPException(status_code=409, detail="after-action artifact is not available for this legacy run")
        import json

        return json.loads(path.read_text(encoding="utf-8"))

    @app.get("/api/v1/runs/{run_id}/verification")
    def verification(run_id: str) -> dict[str, Any]:
        loaded = load_run(run_id)
        manifest = dict(loaded["manifest"])
        integrity = verify_run_integrity(run_id)
        manifest["integrity"] = integrity
        manifest["missing_files"] = integrity["missing"]
        manifest["mismatched_files"] = integrity["mismatched"]
        manifest["unchecked_files"] = integrity["unchecked"]
        manifest["verification_status"] = integrity["verification_status"]
        return manifest

    @app.websocket("/api/v1/stream")
    async def stream(
        websocket: WebSocket,
        run_id: str | None = None,
        after_sequence: int = -1,
        speed: float | None = None,
    ) -> None:
        await websocket.accept()
        try:
            if speed is not None and speed not in {0.5, 1.0, 2.0, 4.0, 16.0}:
                await websocket.close(code=1008, reason="unsupported replay speed")
                return
            selected = _require_run(run_id or app.state.default_run_id)
            all_snapshots = _read_run_file(selected, "events.jsonl")
            final_sequence = all_snapshots[-1]["sequence"]
            snapshots = [item for item in all_snapshots if int(item["sequence"]) > after_sequence]
            if not snapshots:
                await websocket.close(code=1000, reason="replay already complete")
                return
            decisions_data = _read_run_file(selected, "decisions.jsonl")
            verification = _verification_summary(selected)
            prior_sim_time = snapshots[0]["sim_time_s"]
            for snapshot in snapshots:
                delay = (
                    max(0.0, float(snapshot["sim_time_s"]) - float(prior_sim_time)) / speed
                    if speed is not None
                    else 0.0
                )
                if delay:
                    await asyncio.sleep(min(delay, 1.0))
                payload = _merge_snapshot(
                    snapshot,
                    decisions_data,
                    verification if snapshot["sequence"] == final_sequence else None,
                )
                await websocket.send_json(
                    {
                        "schema_version": "1.0",
                        "message_type": "snapshot",
                        "run_id": selected,
                        "sequence": snapshot["sequence"],
                        "sim_time_s": snapshot["sim_time_s"],
                        "recorded_at": snapshot["recorded_at"],
                        "payload": payload,
                    }
                )
                prior_sim_time = snapshot["sim_time_s"]
            final = snapshots[-1]
            await websocket.send_json(
                {
                    "schema_version": "1.0",
                    "message_type": "status",
                    "run_id": selected,
                    "sequence": final["sequence"],
                    "sim_time_s": final["sim_time_s"],
                    "recorded_at": final["recorded_at"],
                    "status": "replay_complete",
                    "payload": {"status": "replay_complete"},
                }
            )
        finally:
            await websocket.close()

    return app


def _select_run(run_id: str | None) -> str | None:
    if run_id:
        return run_id
    runs = list_runs()
    return runs[0]["run_id"] if runs else None


def _require_run(run_id: str | None) -> str:
    selected = _select_run(run_id)
    if not selected:
        raise HTTPException(status_code=404, detail="no evidence runs available")
    try:
        load_run(selected)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return selected


def _read_run_file(run_id: str, name: str) -> list[dict[str, Any]]:
    path = RUNS_DIR / run_id / name
    if not path.exists():
        raise HTTPException(status_code=409, detail=f"evidence file is missing: {name}")
    return read_jsonl(path)


def _merge_snapshot(
    snapshot: dict[str, Any],
    decisions: list[dict[str, Any]],
    verification: dict[str, Any] | None = None,
) -> dict[str, Any]:
    active = next((item for item in reversed(decisions) if item["sequence"] <= snapshot["sequence"]), None)
    merged = dict(snapshot)
    for key in ["operator_link_available", "navigation_confidence", "energy_margin_wh"]:
        merged[key] = snapshot[key]["value"]
        merged[f"{key}_age_s"] = snapshot["sim_time_s"] - snapshot[key]["source_time_s"]
        merged[f"{key}_valid"] = snapshot[key]["valid"]
    delivery = snapshot.get("delivery") or {}
    merged.update(
        {
            "mission_id": delivery.get("mission_id"),
            "request_id": delivery.get("request_id"),
            "package_id": delivery.get("package_id"),
            "recipient_id": delivery.get("recipient_id"),
            "package_custody": delivery.get("custody", "NOT_MODELED"),
            "receipt_status": delivery.get("receipt_status", "NOT_MODELED"),
            "delivery_outcome": delivery.get("outcome", "NOT_MODELED"),
            "timeliness": delivery.get("timeliness", "NOT_MODELED"),
            "delivery_zone_arrived": delivery.get("delivery_zone_arrived", False),
            "landed_at_site": delivery.get("landed_at_site", False),
            "disarmed_at_site": delivery.get("disarmed_at_site", False),
            "handoff_progress": delivery.get("handoff_progress", 0.0),
            "deadline_remaining_s": delivery.get("deadline_remaining_s"),
            "accepted_at_s": delivery.get("accepted_at_s"),
            "delivery_source": delivery.get("source", "not-modeled"),
        }
    )
    if active:
        merged.update(
            {
                "assurance_state": active["new_state"],
                "recommended_action": active["recommended_action"],
                "decision_code": active["decision_code"],
                "decision_summary": active["summary"],
                "requirement_ids": active["requirement_ids"],
                "hazard_ids": active["hazard_ids"],
                "rejected_actions": active["rejected_actions"],
            }
        )
    if verification:
        merged.update(verification)
    return merged


def _verification_summary(run_id: str) -> dict[str, Any]:
    integrity = verify_run_integrity(run_id)
    issue_count = len(integrity["missing"]) + len(integrity["mismatched"]) + len(integrity["unchecked"])
    return {
        "verification_status": integrity["verification_status"],
        "evidence_complete": integrity["complete"],
        "evidence_issue_count": issue_count,
    }


def _value_for_key(point: dict[str, Any], key: str) -> Any:
    return point.get(key)


def _run_catalog_item(manifest: dict[str, Any]) -> dict[str, Any]:
    run_id = manifest["run_id"]
    summary_path = RUNS_DIR / run_id / "run-summary.json"
    summary = {}
    if summary_path.exists():
        import json

        summary = json.loads(summary_path.read_text(encoding="utf-8"))
    return {
        "run_id": run_id,
        "scenario_id": manifest.get("scenario_id"),
        "source": manifest.get("software_versions", {}).get("source", "unknown"),
        "verification_status": manifest.get("verification_status", "UNKNOWN"),
        "aircraft_outcome": summary.get("aircraft_outcome", "LEGACY_NOT_MODELED"),
        "delivery_outcome": summary.get("delivery_outcome", "LEGACY_NOT_MODELED"),
        "timeliness": summary.get("timeliness", "LEGACY_NOT_MODELED"),
        "terminal_state": summary.get("terminal_state", "UNKNOWN"),
        "exploratory": manifest.get("exploratory", False),
    }
