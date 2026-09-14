import asyncio

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
from lifeline.telemetry.mavsdk_adapter import VehicleSample


class FakeAdapter:
    instances = []

    def __init__(self, config, *, allow_sitl_actions=False):
        self.tick = 0
        self.landed = False
        self.commands = []
        self.instances.append(self)

    async def connect(self):
        return None

    async def wait_ready(self):
        return None

    async def upload_fictional_mission(self):
        return None

    async def arm_and_start(self):
        return None

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
    assert all(result.passed for result in run.assertions)
