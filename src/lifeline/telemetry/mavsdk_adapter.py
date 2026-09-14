from __future__ import annotations

import asyncio
import math
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from lifeline.config import LifelineConfig
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

    async def wait_ready(self, timeout_s: float = 45.0) -> None:
        self._require_drone()

        async def wait_health() -> None:
            async for health in self._drone.telemetry.health():
                if health.is_global_position_ok and health.is_home_position_ok:
                    return

        await asyncio.wait_for(wait_health(), timeout=timeout_s)

    async def upload_fictional_mission(self) -> None:
        self._require_actions()
        self._require_drone()
        from mavsdk.mission import MissionItem, MissionPlan

        home = await _first(self._drone.telemetry.home())
        offsets = [(0.0, 0.0), (120.0, 35.0), (240.0, 80.0), (0.0, 0.0)]
        items = []
        for north_m, east_m in offsets:
            latitude, longitude = _offset_lat_lon(home.latitude_deg, home.longitude_deg, north_m, east_m)
            items.append(
                MissionItem(
                    latitude,
                    longitude,
                    25.0,
                    8.0,
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

    async def arm_and_start(self) -> None:
        self._require_actions()
        self._require_drone()
        await self._drone.action.arm()
        await self._drone.mission.start_mission()

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
        position, battery, velocity, mode = await asyncio.gather(
            _first(self._drone.telemetry.position()),
            _first(self._drone.telemetry.battery()),
            _first(self._drone.telemetry.velocity_ned()),
            _first(self._drone.telemetry.flight_mode()),
        )
        speed = math.hypot(velocity.north_m_s, velocity.east_m_s)
        return VehicleSample(
            connected=True,
            latitude_deg=position.latitude_deg,
            longitude_deg=position.longitude_deg,
            relative_altitude_m=max(0.0, position.relative_altitude_m),
            battery_remaining_pct=max(0.0, min(100.0, battery.remaining_percent * 100.0)),
            ground_speed_mps=max(0.0, speed),
            flight_mode=str(mode),
        )

    async def mission_progress(self) -> tuple[int, int]:
        self._require_drone()
        progress = await _first(self._drone.mission.mission_progress())
        return progress.current, progress.total

    async def in_air(self) -> bool:
        self._require_drone()
        return bool(await _first(self._drone.telemetry.in_air()))

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
