from __future__ import annotations

import asyncio
import math
from datetime import UTC, datetime
from time import monotonic

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
from lifeline.scenarios.runner import ScenarioRun
from lifeline.telemetry import MavsdkAdapter
from lifeline.telemetry.mavsdk_adapter import SitlSafetyError, VehicleSample


async def run_px4_scenario(
    scenario: ScenarioDefinition,
    config: LifelineConfig,
    *,
    allow_sitl_actions: bool,
    run_id: str | None = None,
    exploratory: bool = False,
) -> ScenarioRun:
    """Run a scenario against an explicitly authorized localhost PX4 SITL."""
    if not allow_sitl_actions or not config.sitl.actions_enabled:
        raise SitlSafetyError("PX4 execution requires both --allow-sitl-actions and config sitl.actions_enabled=true")

    adapter = MavsdkAdapter(config, allow_sitl_actions=allow_sitl_actions)
    await adapter.connect()
    await adapter.wait_ready()
    await adapter.upload_fictional_mission()
    await adapter.arm_and_start()

    run_id = run_id or f"LFL-{scenario.id.replace('-', '')}-PX4-{datetime.now(UTC):%Y%m%dT%H%M%SZ}"
    engine = AssuranceEngine(config)
    context = EngineContext()
    snapshots: list[MissionSnapshot] = []
    decisions: list[DecisionRecord] = []
    overrides: dict[str, bool | float | str] = {}
    source_times = {"link": 0.0, "nav": 0.0, "energy": 0.0}
    previous_signature: tuple | None = None
    previous_command = RecommendedAction.NONE
    last_sample: VehicleSample | None = None
    home: tuple[float, float] | None = None
    event_index = 0
    sequence = 0
    ever_airborne = False
    terminal_requested = False
    started_at = monotonic()

    while True:
        now = round(monotonic() - started_at, 3)
        while event_index < len(scenario.events) and scenario.events[event_index].at_s <= now:
            overrides.update(scenario.events[event_index].set)
            event_index += 1

        sample_valid = True
        try:
            sample = await adapter.sample()
            current, total = await adapter.mission_progress()
            airborne = await adapter.in_air()
            last_sample = sample
            if home is None:
                home = (sample.latitude_deg, sample.longitude_deg)
        except Exception:
            sample_valid = False
            sample = last_sample or _unavailable_sample()
            current, total, airborne = 0, 0, False

        ever_airborne = ever_airborne or airborne
        progress = max(0.0, min(1.0, current / total if total else 0.0))
        mission_state, delivered = _mission_state(progress, airborne, ever_airborne, terminal_requested)
        north_m, east_m = _local_position(sample, home)
        energy_available = (sample.battery_remaining_pct / 100.0) * config.energy.usable_capacity_wh
        energy_reserve = config.energy.usable_capacity_wh * config.energy.protected_reserve_fraction
        energy_recovery = 20.0
        modeled_margin = energy_available - energy_recovery - energy_reserve
        energy_margin = float(overrides.get("energy_margin_wh", modeled_margin))
        navigation = float(overrides.get("navigation_confidence", 0.90))
        link = bool(overrides.get("operator_link_available", sample_valid and sample.connected))

        if sample_valid and not bool(overrides.get("freeze_telemetry", False)):
            source_times = {"link": now, "nav": now, "energy": now}

        snapshot = MissionSnapshot(
            run_id=run_id,
            sequence=sequence,
            sim_time_s=now,
            mission_state=mission_state,
            operator_link_available=CriticalValue(
                value=link, source_time_s=source_times["link"], receipt_time_s=now, valid=sample_valid, source="mavsdk"
            ),
            navigation_confidence=CriticalValue(
                value=navigation, source_time_s=source_times["nav"], receipt_time_s=now, valid=sample_valid, source="mavsdk"
            ),
            energy_margin_wh=CriticalValue(
                value=energy_margin, source_time_s=source_times["energy"], receipt_time_s=now, valid=sample_valid, source="model"
            ),
            battery_remaining_pct=sample.battery_remaining_pct,
            energy_available_wh=energy_available,
            energy_recovery_wh=energy_recovery,
            energy_reserve_wh=energy_reserve,
            route_progress=progress,
            north_m=north_m,
            east_m=east_m,
            relative_altitude_m=sample.relative_altitude_m,
            ground_speed_mps=sample.ground_speed_mps,
            flight_mode=sample.flight_mode,
            vehicle_connected=sample_valid and sample.connected,
            payload_delivered=delivered,
            exploratory=exploratory,
        )
        record, context = engine.evaluate(snapshot, context)
        snapshots.append(snapshot)
        signature = (record.new_state, record.recommended_action, record.decision_code)
        if signature != previous_signature:
            decisions.append(record)
            previous_signature = signature

        command = record.recommended_action
        if command != previous_command and command in {
            RecommendedAction.RETURN,
            RecommendedAction.CONTROLLED_LAND,
        }:
            await adapter.execute(command)
            previous_command = command
            terminal_requested = command == RecommendedAction.CONTROLLED_LAND

        sequence += 1
        if mission_state in {MissionState.RECOVERED, MissionState.SAFE_STOP, MissionState.ABORTED}:
            break
        if now >= scenario.duration_s:
            break
        next_tick = started_at + sequence * scenario.tick_s
        await asyncio.sleep(max(0.0, next_tick - monotonic()))

    assertions = evaluate_expectations(scenario, snapshots, decisions)
    return ScenarioRun(run_id, scenario, snapshots, decisions, assertions, "px4")


def _mission_state(progress: float, airborne: bool, ever_airborne: bool, terminal_requested: bool) -> tuple[MissionState, bool]:
    if terminal_requested:
        return (MissionState.LANDING if airborne else MissionState.SAFE_STOP), False
    if not ever_airborne:
        return MissionState.PREFLIGHT, False
    if not airborne:
        return MissionState.RECOVERED, progress >= 0.5
    if progress < 0.50:
        return MissionState.OUTBOUND, False
    if progress < 0.75:
        return MissionState.DELIVERY, True
    return MissionState.RETURNING, True


def _unavailable_sample() -> VehicleSample:
    return VehicleSample(False, 0.0, 0.0, 0.0, 0.0, 0.0, "UNKNOWN")


def _local_position(sample: VehicleSample, home: tuple[float, float] | None) -> tuple[float, float]:
    if home is None:
        return 0.0, 0.0
    earth_radius_m = 6_378_137.0
    latitude_delta = math.radians(sample.latitude_deg - home[0])
    longitude_delta = math.radians(sample.longitude_deg - home[1])
    north_m = latitude_delta * earth_radius_m
    east_m = longitude_delta * earth_radius_m * math.cos(math.radians(home[0]))
    return north_m, east_m
