import asyncio

import pytest

from lifeline.config import load_config
from lifeline.models import (
    MissionState,
    RecommendedAction,
    ScenarioDefinition,
    ScenarioEvent,
    ScenarioExpectation,
    TraceLinks,
)
from lifeline.scenarios import px4_runner
from lifeline.telemetry.mavsdk_adapter import SitlSafetyError, VehicleSample


class FakeAdapter:
    instances = []

    def __init__(self, config, *, allow_sitl_actions=False):
        self.tick = 0
        self.landed = False
        self.commands = []
        self.vehicle_uuid = 4242
        self.instances.append(self)

    async def connect(self):
        return None

    async def wait_ready(self):
        return None

    async def upload_fictional_mission(self):
        return "accepted:upload_mission"

    async def arm(self):
        return "accepted:arm"

    async def start_mission(self):
        return "accepted:start_mission"

    async def sample(self):
        self.tick += 1
        return VehicleSample(True, 47.0, -122.0, 25.0, 80.0, 8.0, "MISSION")

    async def mission_progress(self):
        return min(self.tick, 4), 4

    async def in_air(self):
        return not self.landed and self.tick < 4

    async def execute(self, action):
        self.commands.append(action)
        if action == RecommendedAction.CONTROLLED_LAND:
            self.landed = True
        return "accepted"


def _enabled_config():
    config = load_config()
    return config.model_copy(update={"sitl": config.sitl.model_copy(update={"actions_enabled": True})})


def _scenario(*, navigation_fault=False):
    return ScenarioDefinition(
        id="T-99",
        name="PX4 adapter component scenario",
        duration_s=0.10,
        tick_s=0.01,
        events=[ScenarioEvent(at_s=0, set={"navigation_confidence": 0.20})] if navigation_fault else [],
        expect=ScenarioExpectation(
            terminal_state=MissionState.SAFE_STOP if navigation_fault else MissionState.RECOVERED,
            prohibited_actions=[RecommendedAction.RETURN] if navigation_fault else [],
            required_decision_codes=["NAVIGATION_INVALID"] if navigation_fault else [],
        ),
        trace=TraceLinks(requirements=["REQ-ASSUR-004"], hazards=["HZ-003"]),
    )


def test_px4_runner_normalizes_simulator_telemetry(monkeypatch):
    FakeAdapter.instances.clear()
    monkeypatch.setattr(px4_runner, "MavsdkAdapter", FakeAdapter)
    run = asyncio.run(
        px4_runner.run_px4_scenario(
            _scenario(),
            _enabled_config(),
            allow_sitl_actions=True,
        )
    )
    assert run.source == "px4"
    assert run.snapshots[-1].mission_state == MissionState.RECOVERED
    assert [record.command.value for record in run.commands[:3]] == ["UPLOAD_MISSION", "ARM", "START_MISSION"]
    assert all(record.accepted for record in run.commands)
    assert run.environment["vehicle_uuid"] == "4242"
    assert all(
        snapshot.energy_margin_wh.source_time_s <= snapshot.energy_margin_wh.receipt_time_s for snapshot in run.snapshots
    )
    assert all(result.passed for result in run.assertions)


def test_px4_runner_executes_controlled_land_for_invalid_navigation(monkeypatch):
    FakeAdapter.instances.clear()
    monkeypatch.setattr(px4_runner, "MavsdkAdapter", FakeAdapter)
    run = asyncio.run(
        px4_runner.run_px4_scenario(
            _scenario(navigation_fault=True),
            _enabled_config(),
            allow_sitl_actions=True,
        )
    )
    assert run.snapshots[-1].mission_state == MissionState.SAFE_STOP
    assert RecommendedAction.CONTROLLED_LAND in FakeAdapter.instances[0].commands
    land = next(record for record in run.commands if record.command.value == "CONTROLLED_LAND")
    assert land.accepted and land.completed_at_s is not None
    assert land.observed_completion_state == "SAFE_STOP"
    assert all(result.passed for result in run.assertions)


def test_px4_runner_rejects_zero_vehicle_uuid(monkeypatch):
    class ZeroUuidAdapter(FakeAdapter):
        def __init__(self, config, *, allow_sitl_actions=False):
            super().__init__(config, allow_sitl_actions=allow_sitl_actions)
            self.vehicle_uuid = 0

    monkeypatch.setattr(px4_runner, "MavsdkAdapter", ZeroUuidAdapter)
    with pytest.raises(SitlSafetyError, match="nonzero vehicle UUID"):
        asyncio.run(px4_runner.run_px4_scenario(_scenario(), _enabled_config(), allow_sitl_actions=True))
