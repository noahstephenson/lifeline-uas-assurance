import asyncio
import sys
from types import SimpleNamespace

import pytest

from lifeline.config import load_config, validate_sitl_qualification
from lifeline.scenarios import load_scenario, run_px4_scenario
from lifeline.telemetry import MavsdkAdapter, SitlSafetyError


def test_actions_are_disabled_by_default():
    adapter = MavsdkAdapter(load_config(), allow_sitl_actions=True)
    assert not adapter.actions_allowed
    assert adapter.endpoint == "udpin://127.0.0.1:14540"


@pytest.mark.parametrize("allow_cli", [False, True])
def test_px4_runner_requires_two_key_action_authorization(allow_cli):
    with pytest.raises(SitlSafetyError, match="requires both"):
        asyncio.run(
            run_px4_scenario(
                load_scenario("T-01"),
                load_config(),
                allow_sitl_actions=allow_cli,
            )
        )


def test_non_loopback_endpoint_is_rejected():
    config = load_config().model_copy(update={"sitl": load_config().sitl.model_copy(update={"endpoint": "udpout://192.168.1.20:14540"})})
    with pytest.raises(SitlSafetyError):
        MavsdkAdapter(config)


class _ConnectedCore:
    async def connection_state(self):
        yield SimpleNamespace(is_connected=True)


class _Info:
    def __init__(self, legacy_uid):
        self.legacy_uid = legacy_uid

    async def get_identification(self):
        return SimpleNamespace(legacy_uid=self.legacy_uid, hardware_uid="0" * 32)


class _System:
    legacy_uid = 4242

    def __init__(self):
        self.core = _ConnectedCore()
        self.info = _Info(self.legacy_uid)

    async def connect(self, *, system_address):
        assert system_address == "udpin://127.0.0.1:14540"


def test_connect_uses_mavsdk_identification_legacy_uuid(monkeypatch):
    monkeypatch.setitem(sys.modules, "mavsdk", SimpleNamespace(System=_System))
    adapter = MavsdkAdapter(validate_sitl_qualification(), allow_sitl_actions=True)
    asyncio.run(adapter.connect(timeout_s=0.1))
    assert adapter.vehicle_uuid == 4242


def test_connect_rejects_zero_identification_uuid(monkeypatch):
    class ZeroUuidSystem(_System):
        legacy_uid = 0

    monkeypatch.setitem(sys.modules, "mavsdk", SimpleNamespace(System=ZeroUuidSystem))
    adapter = MavsdkAdapter(validate_sitl_qualification(), allow_sitl_actions=True)
    with pytest.raises(SitlSafetyError, match="zero legacy UUID"):
        asyncio.run(adapter.connect(timeout_s=0.1))


def test_telemetry_subscriptions_are_persistent_and_cached():
    calls: dict[str, int] = {}

    async def stream(name, value):
        calls[name] = calls.get(name, 0) + 1
        yield value
        await asyncio.Event().wait()

    telemetry = SimpleNamespace(
        position=lambda: stream("position", SimpleNamespace(latitude_deg=47.0, longitude_deg=-122.0, relative_altitude_m=8.0)),
        battery=lambda: stream("battery", SimpleNamespace(remaining_percent=0.8)),
        velocity_ned=lambda: stream("velocity", SimpleNamespace(north_m_s=3.0, east_m_s=4.0)),
        flight_mode=lambda: stream("mode", "MISSION"),
        in_air=lambda: stream("in_air", True),
        armed=lambda: stream("armed", True),
    )
    mission = SimpleNamespace(mission_progress=lambda: stream("progress", SimpleNamespace(current=2, total=4)))

    async def exercise():
        adapter = MavsdkAdapter(validate_sitl_qualification(), allow_sitl_actions=True)
        adapter._drone = SimpleNamespace(telemetry=telemetry, mission=mission)
        first = await adapter.sample()
        second = await adapter.sample()
        assert first == second
        assert await adapter.mission_progress() == (2, 4)
        assert await adapter.mission_progress() == (2, 4)
        assert await adapter.in_air()
        assert await adapter.in_air()
        assert await adapter.armed()
        assert await adapter.armed()
        assert first.received_at_monotonic_s > 0
        assert first.link_received_at_monotonic_s > 0
        assert first.navigation_received_at_monotonic_s > 0
        assert first.energy_received_at_monotonic_s > 0

    asyncio.run(exercise())
    assert calls == {"position": 1, "battery": 1, "velocity": 1, "mode": 1, "progress": 1, "in_air": 1, "armed": 1}


def test_wait_ready_requests_two_hz_critical_telemetry():
    rates: dict[str, float] = {}

    async def set_rate(name, value):
        rates[name] = value

    async def health():
        yield SimpleNamespace(is_local_position_ok=True, is_global_position_ok=True, is_home_position_ok=True, is_armable=True)

    telemetry = SimpleNamespace(
        set_rate_position=lambda value: set_rate("position", value),
        set_rate_velocity_ned=lambda value: set_rate("velocity", value),
        set_rate_battery=lambda value: set_rate("battery", value),
        set_rate_in_air=lambda value: set_rate("in_air", value),
        health=health,
    )

    async def exercise():
        adapter = MavsdkAdapter(validate_sitl_qualification(), allow_sitl_actions=True)
        adapter._drone = SimpleNamespace(telemetry=telemetry)
        await adapter.wait_ready(timeout_s=0.1)

    asyncio.run(exercise())
    assert rates == {"position": 2.0, "velocity": 2.0, "battery": 2.0, "in_air": 2.0}


def test_qualification_profile_differs_only_by_action_flag(tmp_path):
    assert validate_sitl_qualification().sitl.actions_enabled
    profile = load_config().model_copy(
        update={
            "decision_rate_hz": 4.0,
            "sitl": load_config().sitl.model_copy(update={"actions_enabled": True}),
        }
    )
    path = tmp_path / "changed.yaml"
    import yaml

    path.write_text(yaml.safe_dump(profile.model_dump(mode="json")), encoding="utf-8")
    with pytest.raises(ValueError, match="only by actions_enabled"):
        validate_sitl_qualification(path)
