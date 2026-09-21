from __future__ import annotations

import asyncio
import math
from dataclasses import dataclass
from pathlib import Path
from time import monotonic
from typing import Any
from urllib.parse import urlparse

import yaml

from lifeline.config import PROJECT_ROOT, LifelineConfig
from lifeline.models import RecommendedAction


class SitlSafetyError(RuntimeError):
    pass


@dataclass(frozen=True)
class VehicleSample:
    connected: bool
    latitude_deg: float
    longitude_deg: float
    relative_altitude_m: float
    battery_remaining_pct: float
    ground_speed_mps: float
    flight_mode: str
    received_at_monotonic_s: float = 0.0
    link_received_at_monotonic_s: float = 0.0
    navigation_received_at_monotonic_s: float = 0.0
    energy_received_at_monotonic_s: float = 0.0


class MavsdkAdapter:
    """Narrow MAVSDK boundary. Importing this module does not require MAVSDK."""

    def __init__(
        self,
        config: LifelineConfig,
        *,
        allow_sitl_actions: bool = False,
    ) -> None:
        self.config = config
        self.endpoint = config.sitl.endpoint
        self.actions_allowed = bool(allow_sitl_actions and config.sitl.actions_enabled)
        self._validate_loopback_endpoint()
        self._drone: Any | None = None
        self.vehicle_uuid: int | None = None
        self._stream_tasks: dict[str, asyncio.Task[None]] = {}
        self._stream_events: dict[str, asyncio.Event] = {}
        self._stream_values: dict[str, Any] = {}
        self._stream_received_at: dict[str, float] = {}
        self._stream_errors: dict[str, BaseException] = {}

    def _validate_loopback_endpoint(self) -> None:
        endpoint = self.endpoint.replace("udpin://", "udp://", 1).replace("udpout://", "udp://", 1)
        parsed = urlparse(endpoint)
        if parsed.scheme not in {"udp", "tcp"} or parsed.hostname not in self.config.sitl.allowed_hosts:
            raise SitlSafetyError("PX4 endpoint is not an explicitly allowlisted local SITL endpoint")

    async def connect(self, timeout_s: float = 20.0) -> None:
        try:
            from mavsdk import System
        except ImportError as exc:
            raise RuntimeError("install the px4 extra: pip install -e '.[px4]'") from exc
        self._drone = System()
        await self._drone.connect(system_address=self.endpoint)

        async def wait_connected() -> None:
            async for state in self._drone.core.connection_state():
                if state.is_connected:
                    return

        await asyncio.wait_for(wait_connected(), timeout=timeout_s)
        identification = await asyncio.wait_for(self._drone.info.get_identification(), timeout=timeout_s)
        if not identification.legacy_uid:
            raise SitlSafetyError("connected SITL reported an invalid zero legacy UUID")
        self.vehicle_uuid = int(identification.legacy_uid)

    async def wait_ready(self, timeout_s: float = 45.0) -> None:
        self._require_drone()

        async def wait_health() -> None:
            async for health in self._drone.telemetry.health():
                if health.is_global_position_ok and health.is_home_position_ok:
                    return

        await asyncio.wait_for(wait_health(), timeout=timeout_s)

    async def upload_fictional_mission(self, mission_path: Path | None = None) -> str:
        self._require_actions()
        self._require_drone()
        from mavsdk.mission import MissionItem, MissionPlan

        home = await _first(self._drone.telemetry.home())
        mission_path = mission_path or PROJECT_ROOT / "config" / "missions" / "medical-resupply.yaml"
        mission = yaml.safe_load(mission_path.read_text(encoding="utf-8"))
        if mission.get("coordinate_frame") != "local_ned":
            raise SitlSafetyError("qualification mission must use the fictional local_ned frame")
        offsets = [
            (
                float(item["north_m"]),
                float(item["east_m"]),
                float(item["altitude_m"]),
            )
            for item in mission["route"]
        ]
        items = []
        for north_m, east_m, altitude_m in offsets:
            latitude, longitude = _offset_lat_lon(home.latitude_deg, home.longitude_deg, north_m, east_m)
            items.append(
                MissionItem(
                    latitude,
                    longitude,
                    max(1.0, altitude_m),
                    float(mission["cruise_speed_mps"]),
                    True,
                    float("nan"),
                    float("nan"),
                    MissionItem.CameraAction.NONE,
                    float("nan"),
                    float("nan"),
                    float("nan"),
                    float("nan"),
                    float("nan"),
                    MissionItem.VehicleAction.NONE,
                )
            )
        await self._drone.mission.set_return_to_launch_after_mission(True)
        await self._drone.mission.upload_mission(MissionPlan(items))
        return "accepted:upload_mission"

    async def arm(self) -> str:
        self._require_actions()
        self._require_drone()
        await self._drone.action.arm()
        return "accepted:arm"

    async def start_mission(self) -> str:
        self._require_actions()
        self._require_drone()
        await self._drone.mission.start_mission()
        return "accepted:start_mission"

    async def takeoff(self, altitude_m: float = 8.0) -> str:
        self._require_actions()
        self._require_drone()
        await self._drone.action.set_takeoff_altitude(altitude_m)
        await self._drone.action.takeoff()
        return "accepted:takeoff"

    async def land(self) -> str:
        self._require_actions()
        self._require_drone()
        await self._drone.action.land()
        return "accepted:land"

    async def execute(self, action: RecommendedAction) -> str:
        self._require_actions()
        self._require_drone()
        if action == RecommendedAction.RETURN:
            await self._drone.action.return_to_launch()
            return "accepted:return_to_launch"
        if action == RecommendedAction.CONTROLLED_LAND:
            await self._drone.action.land()
            return "accepted:land"
        if action in {RecommendedAction.NONE, RecommendedAction.CONTINUE}:
            return "accepted:no_command"
        raise SitlSafetyError(f"action is not mapped to PX4: {action.value}")

    async def sample(self) -> VehicleSample:
        self._require_drone()
        position_result, battery_result, velocity_result, mode_result = await asyncio.gather(
            self._stream_value("position", self._drone.telemetry.position),
            self._stream_value("battery", self._drone.telemetry.battery),
            self._stream_value("velocity_ned", self._drone.telemetry.velocity_ned),
            self._stream_value("flight_mode", self._drone.telemetry.flight_mode),
        )
        position, position_at = position_result
        battery, battery_at = battery_result
        velocity, velocity_at = velocity_result
        mode, mode_at = mode_result
        speed = math.hypot(velocity.north_m_s, velocity.east_m_s)
        return VehicleSample(
            connected=True,
            latitude_deg=position.latitude_deg,
            longitude_deg=position.longitude_deg,
            relative_altitude_m=max(0.0, position.relative_altitude_m),
            battery_remaining_pct=max(0.0, min(100.0, battery.remaining_percent * 100.0)),
            ground_speed_mps=max(0.0, speed),
            flight_mode=str(mode),
            received_at_monotonic_s=min(position_at, battery_at, velocity_at, mode_at),
            link_received_at_monotonic_s=position_at,
            navigation_received_at_monotonic_s=min(position_at, velocity_at),
            energy_received_at_monotonic_s=battery_at,
        )

    async def mission_progress(self) -> tuple[int, int]:
        self._require_drone()
        progress, _ = await self._stream_value("mission_progress", self._drone.mission.mission_progress)
        return progress.current, progress.total

    async def in_air(self) -> bool:
        self._require_drone()
        value, _ = await self._stream_value("in_air", self._drone.telemetry.in_air)
        return bool(value)

    async def _stream_value(self, key: str, factory: Any, timeout_s: float = 5.0) -> tuple[Any, float]:
        if key not in self._stream_tasks:
            event = asyncio.Event()
            self._stream_events[key] = event
            self._stream_tasks[key] = asyncio.create_task(self._consume_stream(key, factory()), name=f"mavsdk-{key}")
        await asyncio.wait_for(self._stream_events[key].wait(), timeout=timeout_s)
        if key in self._stream_errors:
            error = self._stream_errors[key]
            raise RuntimeError(f"MAVSDK {key} stream failed: {type(error).__name__}: {error}") from error
        return self._stream_values[key], self._stream_received_at[key]

    async def _consume_stream(self, key: str, stream: Any) -> None:
        try:
            async for value in stream:
                self._stream_values[key] = value
                self._stream_received_at[key] = monotonic()
                self._stream_events[key].set()
            raise RuntimeError("stream ended")
        except asyncio.CancelledError:
            raise
        except BaseException as exc:
            self._stream_errors[key] = exc
            self._stream_events[key].set()

    def _require_drone(self) -> None:
        if self._drone is None:
            raise RuntimeError("MAVSDK is not connected")

    def _require_actions(self) -> None:
        if not self.actions_allowed:
            raise SitlSafetyError("SITL actions require config sitl.actions_enabled=true and --allow-sitl-actions")


async def _first(stream: Any) -> Any:
    async for item in stream:
        return item
    raise RuntimeError("telemetry stream ended before producing a value")


def _offset_lat_lon(latitude_deg: float, longitude_deg: float, north_m: float, east_m: float) -> tuple[float, float]:
    earth_radius_m = 6_378_137.0
    latitude = latitude_deg + math.degrees(north_m / earth_radius_m)
    longitude = longitude_deg + math.degrees(east_m / (earth_radius_m * math.cos(math.radians(latitude_deg))))
    return latitude, longitude
