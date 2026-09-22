from __future__ import annotations

import asyncio
import inspect
import math
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from time import monotonic
from typing import Any

from lifeline.assurance import AssuranceEngine
from lifeline.config import LifelineConfig
from lifeline.delivery import DeliveryThread, load_mission_contract
from lifeline.models import (
    CommandName,
    CommandRecord,
    CriticalValue,
    DecisionRecord,
    DeliveryOutcome,
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
    start_gate: asyncio.Event | None = None,
    on_ready: Callable[[str], Any] | None = None,
    on_snapshot: Callable[[MissionSnapshot, DecisionRecord], Any] | None = None,
    on_command: Callable[[CommandRecord], Any] | None = None,
) -> ScenarioRun:
    """Run a scenario against an explicitly authorized localhost PX4 SITL."""
    if not allow_sitl_actions or not config.sitl.actions_enabled:
        raise SitlSafetyError("PX4 execution requires both --allow-sitl-actions and config sitl.actions_enabled=true")

    adapter = MavsdkAdapter(config, allow_sitl_actions=allow_sitl_actions)
    await adapter.connect()
    if not adapter.vehicle_uuid:
        raise SitlSafetyError("connected SITL must report a nonzero vehicle UUID")
    await adapter.wait_ready()

    run_id = run_id or f"LFL-{scenario.id.replace('-', '')}-PX4-{datetime.now(UTC):%Y%m%dT%H%M%SZ}"
    engine = AssuranceEngine(config)
    context = EngineContext()
    snapshots: list[MissionSnapshot] = []
    decisions: list[DecisionRecord] = []
    commands: list[CommandRecord] = []
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
    contract = load_mission_contract()
    delivery_thread = DeliveryThread(contract)
    delivery_enabled = scenario.expect.delivery_outcome is not None
    recovery_started = False
    recovery_return_commanded = False
    recovery_airborne_observed = False
    initial_departure_observed = False
    site_landing_observed = False
    command_sequence = 0

    async def issue(
        name: CommandName,
        operation: Awaitable[str],
        *,
        decision_sequence: int | None = None,
        requested_at_s: float = 0.0,
    ) -> CommandRecord:
        nonlocal command_sequence
        try:
            acknowledgement = await asyncio.wait_for(operation, timeout=30.0)
            record = CommandRecord(
                sequence=command_sequence,
                command=name,
                requested_at_s=max(0.0, requested_at_s),
                accepted=True,
                acknowledgement=acknowledgement,
                completed_at_s=max(0.0, requested_at_s) if name == CommandName.UPLOAD_MISSION else None,
                decision_sequence=decision_sequence,
                observed_completion_state="ACTION_ACKNOWLEDGED" if name == CommandName.UPLOAD_MISSION else "COMMAND_ACCEPTED",
            )
        except Exception as exc:
            record = CommandRecord(
                sequence=command_sequence,
                command=name,
                requested_at_s=max(0.0, requested_at_s),
                accepted=False,
                acknowledgement="rejected",
                decision_sequence=decision_sequence,
                error=f"{type(exc).__name__}: {exc}",
            )
            commands.append(record)
            command_sequence += 1
            await _notify(on_command, record)
            raise
        commands.append(record)
        command_sequence += 1
        await _notify(on_command, record)
        return record

    await issue(CommandName.UPLOAD_MISSION, adapter.upload_fictional_mission())
    await adapter.sample()
    await adapter.mission_progress()
    await adapter.in_air()
    await adapter.armed()
    await _notify(on_ready, run_id)
    if start_gate is not None:
        await start_gate.wait()
    await issue(CommandName.ARM, adapter.arm())
    await issue(CommandName.START_MISSION, adapter.start_mission())
    started_at = monotonic()
    next_tick = started_at

    while True:
        await asyncio.sleep(max(0.0, next_tick - monotonic()))

        sample_valid = True
        try:
            sample = await adapter.sample()
            current, total = await adapter.mission_progress()
            airborne = await adapter.in_air()
            armed = await adapter.armed()
            last_sample = sample
            if home is None:
                home = (sample.latitude_deg, sample.longitude_deg)
        except Exception:
            sample_valid = False
            sample = last_sample or _unavailable_sample()
            current, total, airborne, armed = 0, 0, False, False

        now = round(monotonic() - started_at, 3)
        while event_index < len(scenario.events) and scenario.events[event_index].at_s <= now:
            overrides.update(scenario.events[event_index].set)
            event_index += 1

        if airborne and not initial_departure_observed:
            initial_departure_observed = True
            _complete_pending_command(commands, CommandName.ARM, now, "AIRBORNE_OUTBOUND_OBSERVED")
            _complete_pending_command(commands, CommandName.START_MISSION, now, "OUTBOUND_TELEMETRY_OBSERVED")
        if recovery_started and airborne and not recovery_airborne_observed:
            recovery_airborne_observed = True
            _complete_pending_command(commands, CommandName.ARM, now, "AIRBORNE_RETURN_LEG_OBSERVED", latest=True)
            _complete_pending_command(commands, CommandName.TAKEOFF, now, "AIRBORNE_RETURN_LEG_OBSERVED", latest=True)
        if recovery_airborne_observed and not recovery_return_commanded:
            await issue(
                CommandName.RETURN,
                adapter.execute(RecommendedAction.RETURN),
                requested_at_s=now,
            )
            recovery_return_commanded = True
        ever_airborne = ever_airborne or airborne
        progress = max(0.0, min(1.0, current / total if total else 0.0))
        north_m, east_m = _local_position(sample, home)
        zone_distance_m = math.hypot(
            north_m - contract.delivery_zone.north_m,
            east_m - contract.delivery_zone.east_m,
        )
        at_delivery_zone = zone_distance_m <= contract.delivery_zone.radius_m
        if delivery_enabled:
            landed_at_delivery_zone = ever_airborne and at_delivery_zone and not airborne and not recovery_started
            disarmed_at_delivery_zone = landed_at_delivery_zone and not armed
            site_landing_observed = site_landing_observed or (
                landed_at_delivery_zone and disarmed_at_delivery_zone
            )
            delivery = delivery_thread.update(
                sim_time_s=now,
                dispatched=ever_airborne,
                at_delivery_zone=at_delivery_zone,
                landed=landed_at_delivery_zone,
                disarmed=disarmed_at_delivery_zone,
                terminal=terminal_requested and not site_landing_observed,
                response_mode=str(overrides.get("receiver_response", "accepted")),
                deadline_s=float(overrides.get("delivery_deadline_s", contract.delivery_deadline_s)),
                aircraft_observation_source="mavsdk-telemetry",
            )
            mission_state = _medical_mission_state(
                airborne=airborne,
                ever_airborne=ever_airborne,
                terminal_requested=terminal_requested,
                site_landing_observed=site_landing_observed,
                recovery_started=recovery_started,
                recovery_airborne_observed=recovery_airborne_observed,
                at_recovery_zone=math.hypot(north_m, east_m) <= contract.delivery_zone.radius_m,
            )
            delivered = delivery.outcome == DeliveryOutcome.ACCEPTED
        else:
            mission_state, delivered = _mission_state(progress, airborne, ever_airborne, terminal_requested)
            delivery = None
        energy_available = (sample.battery_remaining_pct / 100.0) * config.energy.usable_capacity_wh
        energy_reserve = config.energy.usable_capacity_wh * config.energy.protected_reserve_fraction
        energy_recovery = 20.0
        modeled_margin = energy_available - energy_recovery - energy_reserve
        energy_margin = float(overrides.get("energy_margin_wh", modeled_margin))
        navigation_overridden = "navigation_confidence" in overrides
        link_overridden = "operator_link_available" in overrides
        energy_overridden = "energy_margin_wh" in overrides
        navigation = float(overrides.get("navigation_confidence", 0.90))
        link = bool(overrides.get("operator_link_available", sample_valid and sample.connected))

        if sample_valid and not bool(overrides.get("freeze_telemetry", False)):
            received_at = sample.received_at_monotonic_s or monotonic()
            source_times = {
                "link": min(now, _relative_source_time(sample.link_received_at_monotonic_s, received_at, started_at)),
                "nav": min(now, _relative_source_time(sample.navigation_received_at_monotonic_s, received_at, started_at)),
                "energy": min(now, _relative_source_time(sample.energy_received_at_monotonic_s, received_at, started_at)),
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
                valid=sample_valid,
                source="scenario_override" if link_overridden else "mavsdk",
            ),
            navigation_confidence=CriticalValue(
                value=navigation,
                source_time_s=source_times["nav"],
                receipt_time_s=now,
                valid=sample_valid,
                source="scenario_override" if navigation_overridden else "mavsdk",
            ),
            energy_margin_wh=CriticalValue(
                value=energy_margin,
                source_time_s=source_times["energy"],
                receipt_time_s=now,
                valid=sample_valid,
                source="scenario_override" if energy_overridden else "model",
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
            **({"delivery": delivery} if delivery is not None else {}),
            exploratory=exploratory,
        )
        record, context = engine.evaluate(snapshot, context)
        snapshots.append(snapshot)
        signature = (record.new_state, record.recommended_action, record.decision_code)
        if signature != previous_signature:
            decisions.append(record)
            previous_signature = signature
        await _notify(on_snapshot, snapshot, record)

        command = record.recommended_action
        if command != previous_command and command in {
            RecommendedAction.RETURN,
            RecommendedAction.CONTROLLED_LAND,
        }:
            command_name = CommandName.RETURN if command == RecommendedAction.RETURN else CommandName.CONTROLLED_LAND
            await issue(
                command_name,
                adapter.execute(command),
                decision_sequence=record.sequence,
                requested_at_s=now,
            )
            previous_command = command
            terminal_requested = command == RecommendedAction.CONTROLLED_LAND

        if (
            delivery_enabled
            and site_landing_observed
            and not recovery_started
            and delivery.outcome
            in {DeliveryOutcome.ACCEPTED, DeliveryOutcome.REJECTED, DeliveryOutcome.UNCONFIRMED}
        ):
            await issue(CommandName.ARM, adapter.arm(), requested_at_s=now)
            await issue(CommandName.TAKEOFF, adapter.takeoff(), requested_at_s=now)
            recovery_started = True

        sequence += 1
        if mission_state in {MissionState.RECOVERED, MissionState.SAFE_STOP, MissionState.ABORTED}:
            break
        if now >= scenario.duration_s:
            break
        next_tick = monotonic() + scenario.tick_s

    assertions = evaluate_expectations(scenario, snapshots, decisions)
    completed_at = snapshots[-1].sim_time_s if snapshots else 0.0
    for index, command_record in enumerate(commands):
        if command_record.command in {CommandName.RETURN, CommandName.CONTROLLED_LAND} and command_record.accepted:
            commands[index] = command_record.model_copy(
                update={
                    "completed_at_s": completed_at,
                    "observed_completion_state": snapshots[-1].mission_state.value if snapshots else "UNAVAILABLE",
                }
            )
    result = ScenarioRun(
        run_id,
        scenario,
        snapshots,
        decisions,
        assertions,
        "px4",
        commands=commands,
        delivery_events=delivery_thread.events if delivery_enabled else [],
        configuration=config,
        environment={
            "vehicle_uuid": str(adapter.vehicle_uuid or 0),
            "sitl_endpoint": config.sitl.endpoint,
            "aircraft_telemetry": "mavsdk",
            "receiver_source": "modeled-receiving-station",
            "site_disarm_observation": "mavsdk-armed-false",
            "assurance_fault_scope": "scripted-lifeline-inputs-only; PX4 estimator unchanged",
            "return_mode": "mission-to-original-fictional-launch-point",
        },
    )
    await adapter.close()
    return result


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


def _medical_mission_state(
    *,
    airborne: bool,
    ever_airborne: bool,
    terminal_requested: bool,
    site_landing_observed: bool,
    recovery_started: bool,
    recovery_airborne_observed: bool,
    at_recovery_zone: bool,
) -> MissionState:
    if terminal_requested:
        return MissionState.LANDING if airborne else MissionState.SAFE_STOP
    if not ever_airborne:
        return MissionState.PREFLIGHT
    if site_landing_observed and not recovery_started:
        return MissionState.DELIVERY
    if recovery_started:
        if recovery_airborne_observed and not airborne and at_recovery_zone:
            return MissionState.RECOVERED
        return MissionState.RETURNING
    return MissionState.OUTBOUND if airborne else MissionState.LANDING


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


def _complete_pending_command(
    commands: list[CommandRecord],
    name: CommandName,
    completed_at_s: float,
    state: str,
    *,
    latest: bool = False,
) -> None:
    indexes = range(len(commands) - 1, -1, -1) if latest else range(len(commands))
    for index in indexes:
        record = commands[index]
        if record.command == name and record.accepted and record.observed_completion_state == "COMMAND_ACCEPTED":
            commands[index] = record.model_copy(
                update={"completed_at_s": completed_at_s, "observed_completion_state": state}
            )
            return


def _relative_source_time(value: float, fallback: float, started_at: float) -> float:
    return max(0.0, round((value or fallback) - started_at, 3))


async def _notify(callback: Callable[..., Any] | None, *args: Any) -> None:
    if callback is None:
        return
    result = callback(*args)
    if inspect.isawaitable(result):
        await result
