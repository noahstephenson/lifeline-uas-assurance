from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, datetime

from lifeline.assurance import AssuranceEngine
from lifeline.config import LifelineConfig
from lifeline.models import (
    CriticalValue,
    DecisionRecord,
    EngineContext,
    MissionSnapshot,
    MissionState,
    RecommendedAction,
    ScenarioDefinition,
)
from lifeline.scenarios.oracle import evaluate_expectations


@dataclass(frozen=True)
class ScenarioRun:
    run_id: str
    scenario: ScenarioDefinition
    snapshots: list[MissionSnapshot]
    decisions: list[DecisionRecord]
    assertions: list
    source: str = "fake"


def run_scenario(
    scenario: ScenarioDefinition,
    config: LifelineConfig,
    *,
    run_id: str | None = None,
    exploratory: bool = False,
) -> ScenarioRun:
    run_id = run_id or f"LFL-{scenario.id.replace('-', '')}-{datetime.now(UTC):%Y%m%dT%H%M%SZ}"
    engine = AssuranceEngine(config)
    context = EngineContext()
    snapshots: list[MissionSnapshot] = []
    decisions: list[DecisionRecord] = []
    overrides: dict[str, bool | float | str] = {}
    event_index = 0
    source_times = {"link": 0.0, "nav": 0.0, "energy": 0.0}
    forced_return_at: float | None = None
    landing_at: float | None = None
    previous_signature: tuple | None = None
    sequence = 0
    total_ticks = int(math.ceil(scenario.duration_s / scenario.tick_s)) + 1

    for tick in range(total_ticks):
        now = round(tick * scenario.tick_s, 6)
        while event_index < len(scenario.events) and scenario.events[event_index].at_s <= now:
            overrides.update(scenario.events[event_index].set)
            event_index += 1

        if not bool(overrides.get("freeze_telemetry", False)):
            source_times = {"link": now, "nav": now, "energy": now}

        mission_state, progress, delivered = _mission_state(now, forced_return_at, landing_at)
        base_energy = max(8.0, 30.0 - (0.15 * now))
        energy_margin = float(overrides.get("energy_margin_wh", base_energy))
        nav = float(overrides.get("navigation_confidence", 0.90))
        link = bool(overrides.get("operator_link_available", True))
        north_m = 240.0 * min(progress / 0.70, 1.0) if progress <= 0.70 else 240.0 * (1 - progress) / 0.30
        east_m = 80.0 * min(progress / 0.70, 1.0) if progress <= 0.70 else 80.0 * (1 - progress) / 0.30
        airborne = mission_state not in {
            MissionState.PREFLIGHT,
            MissionState.RECOVERED,
            MissionState.SAFE_STOP,
            MissionState.ABORTED,
        }
        snapshot = MissionSnapshot(
            run_id=run_id,
            sequence=sequence,
            sim_time_s=now,
            mission_state=mission_state,
            operator_link_available=CriticalValue(
                value=link,
                source_time_s=source_times["link"],
                receipt_time_s=now,
                source="scenario",
            ),
            navigation_confidence=CriticalValue(
                value=nav,
                source_time_s=source_times["nav"],
                receipt_time_s=now,
                source="scenario",
            ),
            energy_margin_wh=CriticalValue(
                value=energy_margin,
                source_time_s=source_times["energy"],
                receipt_time_s=now,
                source="model",
            ),
            battery_remaining_pct=max(0.0, min(100.0, 70.0 - now * 0.5)),
            energy_available_wh=energy_margin + 40.0,
            energy_recovery_wh=20.0,
            energy_reserve_wh=20.0,
            route_progress=max(0.0, min(1.0, progress)),
            north_m=max(0.0, north_m),
            east_m=max(0.0, east_m),
            relative_altitude_m=25.0 if airborne else 0.0,
            ground_speed_mps=8.0 if airborne and mission_state != MissionState.LANDING else 0.0,
            flight_mode=_flight_mode(mission_state),
            payload_delivered=delivered,
            exploratory=exploratory,
        )
        record, context = engine.evaluate(snapshot, context)
        snapshots.append(snapshot)
        signature = (record.new_state, record.recommended_action, record.decision_code)
        if signature != previous_signature:
            decisions.append(record)
            previous_signature = signature

        if record.recommended_action == RecommendedAction.RETURN and forced_return_at is None:
            forced_return_at = now
        if record.recommended_action == RecommendedAction.CONTROLLED_LAND and landing_at is None:
            landing_at = now

        sequence += 1
        if snapshot.mission_state in {
            MissionState.RECOVERED,
            MissionState.SAFE_STOP,
            MissionState.ABORTED,
        }:
            break

    assertions = evaluate_expectations(scenario, snapshots, decisions)
    return ScenarioRun(run_id, scenario, snapshots, decisions, assertions, "fake")


def _mission_state(now: float, forced_return_at: float | None, landing_at: float | None) -> tuple[MissionState, float, bool]:
    if landing_at is not None:
        if now - landing_at >= 3.0:
            return MissionState.SAFE_STOP, min(now / 60.0, 0.99), False
        return MissionState.LANDING, min(now / 60.0, 0.99), False
    if forced_return_at is not None:
        elapsed = now - forced_return_at
        if elapsed >= 20.0:
            return MissionState.RECOVERED, 1.0, False
        return MissionState.RETURNING, max(0.0, 0.70 * (1 - elapsed / 20.0)), False
    if now < 2.0:
        return MissionState.PREFLIGHT, 0.0, False
    if now < 42.0:
        return MissionState.OUTBOUND, (now - 2.0) / 40.0 * 0.70, False
    if now < 45.0:
        return MissionState.DELIVERY, 0.70, True
    if now < 60.0:
        return MissionState.RETURNING, 0.70 + (now - 45.0) / 15.0 * 0.30, True
    return MissionState.RECOVERED, 1.0, True


def _flight_mode(state: MissionState) -> str:
    return {
        MissionState.PREFLIGHT: "STANDBY",
        MissionState.OUTBOUND: "MISSION",
        MissionState.DELIVERY: "HOLD",
        MissionState.RETURNING: "RETURN_TO_LAUNCH",
        MissionState.LANDING: "LAND",
        MissionState.RECOVERED: "LANDED",
        MissionState.SAFE_STOP: "LANDED",
        MissionState.ABORTED: "ABORTED",
    }.get(state, "UNKNOWN")
