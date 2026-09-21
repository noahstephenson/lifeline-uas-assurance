from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from lifeline.api.app import TELEMETRY_METADATA, _merge_snapshot
from lifeline.config import LifelineConfig
from lifeline.evidence import export_run
from lifeline.models import AssertionResult, CommandRecord, DecisionRecord, MissionSnapshot, ScenarioDefinition
from lifeline.scenarios.px4_runner import run_px4_scenario
from lifeline.scenarios.runner import ScenarioRun


class LiveStatus(StrEnum):
    STARTING = "STARTING"
    WAITING_FOR_VEHICLE = "WAITING_FOR_VEHICLE"
    READY = "READY"
    RUNNING = "RUNNING"
    COMPLETE = "COMPLETE"
    ERROR = "ERROR"


class LiveSession:
    """Own one fail-visible, held PX4 qualification session."""

    def __init__(
        self,
        scenario: ScenarioDefinition,
        config: LifelineConfig,
        *,
        run_id: str,
        start_token: str,
        evidence_root: Path | None = None,
    ) -> None:
        if not start_token:
            raise ValueError("a non-empty one-time start token is required")
        self.scenario = scenario
        self.config = config
        self.run_id = run_id
        self._start_token: str | None = start_token
        self.evidence_root = evidence_root
        self.status = LiveStatus.STARTING
        self.error: str | None = None
        self.snapshots: list[MissionSnapshot] = []
        self.decisions: list[DecisionRecord] = []
        self.commands: list[CommandRecord] = []
        self.dashboard_connected = False
        self.dashboard_connected_at: datetime | None = None
        self.released_at: datetime | None = None
        self._start_gate = asyncio.Event()
        self._lock = asyncio.Lock()
        self._subscribers: set[asyncio.Queue[dict[str, Any]]] = set()
        self._task: asyncio.Task[None] | None = None
        self._last_decision_signature: tuple[str, str, str] | None = None

    def launch(self) -> None:
        if self._task is not None:
            raise RuntimeError("live session already launched")
        self._task = asyncio.create_task(self._run(), name=f"lifeline-live-{self.run_id}")

    async def _run(self) -> None:
        self.status = LiveStatus.WAITING_FOR_VEHICLE
        await self._broadcast_status()
        try:
            run = await run_px4_scenario(
                self.scenario,
                self.config,
                run_id=self.run_id,
                allow_sitl_actions=True,
                start_gate=self._start_gate,
                on_ready=self._ready,
                on_snapshot=self._snapshot,
                on_command=self._command,
            )
            overlap = bool(self.dashboard_connected_at and self.released_at and self.dashboard_connected_at <= self.released_at)
            run.environment.update(
                {
                    "dashboard_connected_at": self.dashboard_connected_at.isoformat() if self.dashboard_connected_at else "unavailable",
                    "mission_released_at": self.released_at.isoformat() if self.released_at else "unavailable",
                    "dashboard_px4_time_overlap": str(overlap).lower(),
                }
            )
            export_run(run, self.evidence_root)
            self.status = LiveStatus.COMPLETE
        except Exception as exc:
            self.error = f"{type(exc).__name__}: {exc}"
            self.status = LiveStatus.ERROR
            failure = ScenarioRun(
                run_id=self.run_id,
                scenario=self.scenario,
                snapshots=self.snapshots,
                decisions=self.decisions,
                assertions=[
                    AssertionResult(
                        name="live_session_completed",
                        passed=False,
                        expected="PX4 session completes and produces required evidence",
                        observed=self.error,
                    )
                ],
                source="px4",
                commands=self.commands,
                configuration=self.config,
                environment={
                    "dashboard_connected_at": self.dashboard_connected_at.isoformat() if self.dashboard_connected_at else "unavailable",
                    "mission_released_at": self.released_at.isoformat() if self.released_at else "unavailable",
                    "dashboard_px4_time_overlap": "false",
                },
                error=self.error,
            )
            try:
                export_run(failure, self.evidence_root)
            except FileExistsError:
                pass
        await self._broadcast_status()

    async def _ready(self, _run_id: str) -> None:
        self.status = LiveStatus.READY
        await self._broadcast_status()

    async def _snapshot(self, snapshot: MissionSnapshot, decision: DecisionRecord) -> None:
        signature = (decision.new_state.value, decision.recommended_action.value, decision.decision_code)
        async with self._lock:
            self.snapshots.append(snapshot)
            if signature != self._last_decision_signature:
                self.decisions.append(decision)
                self._last_decision_signature = signature
            envelope = self._snapshot_envelope(snapshot)
            for queue in self._subscribers:
                queue.put_nowait(envelope)

    async def _command(self, command: CommandRecord) -> None:
        self.commands.append(command)

    def release(self, token: str) -> None:
        if self.status != LiveStatus.READY:
            raise RuntimeError(f"mission cannot start while session is {self.status.value}")
        if not self.dashboard_connected:
            raise RuntimeError("dashboard WebSocket must be connected before mission release")
        if self._start_token is None or token != self._start_token:
            raise PermissionError("invalid or already-used start token")
        self._start_token = None
        self.released_at = datetime.now(UTC)
        self.status = LiveStatus.RUNNING
        self._start_gate.set()

    async def subscribe(self, after_sequence: int) -> tuple[list[dict[str, Any]], asyncio.Queue[dict[str, Any]]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        async with self._lock:
            buffered = [self._snapshot_envelope(item) for item in self.snapshots if item.sequence > after_sequence]
            self._subscribers.add(queue)
            if not self.dashboard_connected:
                self.dashboard_connected = True
                self.dashboard_connected_at = datetime.now(UTC)
        return buffered, queue

    async def unsubscribe(self, queue: asyncio.Queue[dict[str, Any]]) -> None:
        async with self._lock:
            self._subscribers.discard(queue)

    def health(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "mode": "live",
            "run_id": self.run_id,
            "scenario_id": self.scenario.id,
            "dashboard_connected": self.dashboard_connected,
            "sequence": self.snapshots[-1].sequence if self.snapshots else None,
            "error": self.error,
        }

    def history(self, start: float = 0.0, end: float | None = None) -> list[dict[str, Any]]:
        decision_data = [item.model_dump(mode="json") for item in self.decisions]
        points = [
            _merge_snapshot(item.model_dump(mode="json"), decision_data, self._verification_summary())
            for item in self.snapshots
            if item.sim_time_s >= start and (end is None or item.sim_time_s <= end)
        ]
        return points

    def state(self) -> dict[str, Any]:
        if not self.snapshots:
            return {**self.health(), "mission_state": "INITIALIZING", "verification_status": "PENDING"}
        return self.history()[-1]

    async def _broadcast_status(self) -> None:
        envelope = self._status_envelope()
        async with self._lock:
            for queue in self._subscribers:
                queue.put_nowait(envelope)

    def _snapshot_envelope(self, snapshot: MissionSnapshot) -> dict[str, Any]:
        decision_data = [item.model_dump(mode="json") for item in self.decisions]
        return {
            "schema_version": "1.0",
            "message_type": "snapshot",
            "run_id": self.run_id,
            "sequence": snapshot.sequence,
            "sim_time_s": snapshot.sim_time_s,
            "recorded_at": snapshot.recorded_at.isoformat(),
            "payload": _merge_snapshot(snapshot.model_dump(mode="json"), decision_data, self._verification_summary()),
        }

    def _status_envelope(self) -> dict[str, Any]:
        return {
            "schema_version": "1.0",
            "message_type": "status",
            "run_id": self.run_id,
            "sequence": self.snapshots[-1].sequence if self.snapshots else 0,
            "sim_time_s": self.snapshots[-1].sim_time_s if self.snapshots else 0.0,
            "recorded_at": datetime.now(UTC).isoformat(),
            "payload": self.health(),
        }

    def _verification_summary(self) -> dict[str, Any]:
        terminal = self.status in {LiveStatus.COMPLETE, LiveStatus.ERROR}
        return {
            "verification_status": "ERROR" if self.status == LiveStatus.ERROR else "PENDING" if not terminal else "INCOMPLETE",
            "evidence_complete": False,
            "evidence_issue_count": 0 if not terminal else 2,
        }


def finalize_live_setup_error(
    scenario: ScenarioDefinition,
    config: LifelineConfig,
    *,
    run_id: str,
    error: str,
    evidence_root: Path | None = None,
) -> dict[str, Any]:
    """Finalize a reserved live run when orchestration stops before the API can export it."""
    run = ScenarioRun(
        run_id=run_id,
        scenario=scenario,
        snapshots=[],
        decisions=[],
        assertions=[
            AssertionResult(
                name="live_session_completed",
                passed=False,
                expected="PX4 session completes and produces required evidence",
                observed=error,
            )
        ],
        source="px4",
        commands=[],
        configuration=config,
        environment={"dashboard_px4_time_overlap": "false"},
        error=error,
    )
    return export_run(run, evidence_root).model_dump(mode="json")


def create_live_app(session: LiveSession) -> FastAPI:
    app = FastAPI(title="Project Lifeline Live Qualification API", version="1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=r"^http://(127\.0\.0\.1|localhost):\d{2,5}$",
        allow_methods=["GET"],
        allow_headers=["*"],
    )

    @app.on_event("startup")
    async def startup() -> None:
        session.launch()

    @app.get("/api/v1/health")
    async def health() -> dict[str, Any]:
        return session.health()

    @app.get("/api/v1/metadata")
    async def metadata(run_id: str | None = None) -> dict[str, Any]:
        _check_run_id(run_id, session)
        return {"schema_version": "1.0", "run_id": session.run_id, "measurements": TELEMETRY_METADATA}

    @app.get("/api/v1/state")
    async def state(run_id: str | None = None) -> dict[str, Any]:
        _check_run_id(run_id, session)
        return session.state()

    @app.get("/api/v1/history")
    async def history(
        run_id: str | None = None,
        key: str | None = None,
        start: float = Query(default=0, ge=0),
        end: float | None = Query(default=None, ge=0),
    ) -> list[dict[str, Any]]:
        _check_run_id(run_id, session)
        if end is not None and end < start:
            raise HTTPException(status_code=400, detail="end must be greater than or equal to start")
        points = session.history(start, end)
        if key:
            valid = {item["key"] for item in TELEMETRY_METADATA}
            if key not in valid:
                raise HTTPException(status_code=404, detail=f"unknown telemetry key: {key}")
            return [{"timestamp": item["sim_time_s"] * 1000, "value": item.get(key), "id": key} for item in points]
        return points

    @app.post("/api/v1/control/start")
    async def start(request: Request, x_lifeline_start_token: str = Header(default="")) -> dict[str, Any]:
        if request.client is None or request.client.host not in {"127.0.0.1", "::1", "localhost"}:
            raise HTTPException(status_code=403, detail="mission release is loopback-only")
        try:
            session.release(x_lifeline_start_token)
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        await session._broadcast_status()
        return session.health()

    @app.websocket("/api/v1/stream")
    async def stream(websocket: WebSocket, run_id: str | None = None, after_sequence: int = -1) -> None:
        try:
            _check_run_id(run_id, session)
        except HTTPException:
            await websocket.close(code=1008)
            return
        await websocket.accept()
        buffered, queue = await session.subscribe(after_sequence)
        try:
            for envelope in buffered:
                await websocket.send_json(envelope)
            await websocket.send_json(session._status_envelope())
            while True:
                await websocket.send_json(await queue.get())
        except WebSocketDisconnect:
            pass
        finally:
            await session.unsubscribe(queue)

    return app


def _check_run_id(run_id: str | None, session: LiveSession) -> None:
    if run_id is not None and run_id != session.run_id:
        raise HTTPException(status_code=404, detail=f"run not found: {run_id}")
