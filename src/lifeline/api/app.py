from __future__ import annotations

import asyncio
from typing import Any

from fastapi import FastAPI, HTTPException, Query, WebSocket
from fastapi.middleware.cors import CORSMiddleware

from lifeline.evidence.exporter import RUNS_DIR, list_runs, load_run, read_jsonl, verify_run_integrity

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

    @app.get("/api/v1/runs")
    def runs() -> list[dict[str, Any]]:
        return list_runs()

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
        points = [_merge_snapshot(item, decisions, verification) for item in snapshots]
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
    async def stream(websocket: WebSocket, run_id: str | None = None) -> None:
        await websocket.accept()
        try:
            selected = _require_run(run_id or app.state.default_run_id)
            snapshots = _read_run_file(selected, "events.jsonl")
            decisions_data = _read_run_file(selected, "decisions.jsonl")
            verification = _verification_summary(selected)
            for snapshot in snapshots:
                payload = _merge_snapshot(snapshot, decisions_data, verification)
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
                await asyncio.sleep(0.05)
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
