from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

SCHEMA_VERSION = "1.0"


class MissionState(StrEnum):
    INITIALIZING = "INITIALIZING"
    PREFLIGHT = "PREFLIGHT"
    OUTBOUND = "OUTBOUND"
    DELIVERY = "DELIVERY"
    RETURNING = "RETURNING"
    LANDING = "LANDING"
    RECOVERED = "RECOVERED"
    SAFE_STOP = "SAFE_STOP"
    ABORTED = "ABORTED"


class AssuranceState(StrEnum):
    NOMINAL = "NOMINAL"
    WATCH = "WATCH"
    DEGRADED = "DEGRADED"
    RECOVER = "RECOVER"
    TERMINATE = "TERMINATE"
    UNKNOWN = "UNKNOWN"


class RecommendedAction(StrEnum):
    NONE = "NONE"
    CONTINUE = "CONTINUE"
    RETURN = "RETURN"
    CONTROLLED_LAND = "CONTROLLED_LAND"
    ABORT_RUN = "ABORT_RUN"


class VerificationState(StrEnum):
    PENDING = "PENDING"
    PASS = "PASS"
    FAIL = "FAIL"
    ERROR = "ERROR"
    INCOMPLETE = "INCOMPLETE"


class AircraftOutcome(StrEnum):
    PENDING = "PENDING"
    RECOVERED = "RECOVERED"
    SAFE_STOP = "SAFE_STOP"
    ABORTED = "ABORTED"
    INCOMPLETE = "INCOMPLETE"


class PackageCustodyState(StrEnum):
    NOT_MODELED = "NOT_MODELED"
    LOGISTICS_POINT = "LOGISTICS_POINT"
    AIRCRAFT = "AIRCRAFT"
    RECEIVING_STATION = "RECEIVING_STATION"
    RETURNED = "RETURNED"
    UNKNOWN = "UNKNOWN"


class ReceiptStatus(StrEnum):
    NOT_MODELED = "NOT_MODELED"
    PENDING = "PENDING"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    ABSENT = "ABSENT"
    MALFORMED = "MALFORMED"
    STALE = "STALE"
    DUPLICATE = "DUPLICATE"


class DeliveryOutcome(StrEnum):
    NOT_MODELED = "NOT_MODELED"
    PENDING = "PENDING"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    UNCONFIRMED = "UNCONFIRMED"
    NOT_COMPLETED = "NOT_COMPLETED"
    UNKNOWN = "UNKNOWN"


class TimelinessOutcome(StrEnum):
    NOT_MODELED = "NOT_MODELED"
    PENDING = "PENDING"
    ON_TIME = "ON_TIME"
    LATE = "LATE"
    UNKNOWN = "UNKNOWN"


class CommandName(StrEnum):
    UPLOAD_MISSION = "UPLOAD_MISSION"
    ARM = "ARM"
    START_MISSION = "START_MISSION"
    TAKEOFF = "TAKEOFF"
    LAND = "LAND"
    RETURN = "RETURN"
    CONTROLLED_LAND = "CONTROLLED_LAND"


class CriticalValue(BaseModel):
    model_config = ConfigDict(frozen=True)

    value: bool | float
    source_time_s: float = Field(ge=0)
    receipt_time_s: float = Field(ge=0)
    valid: bool = True
    source: str

    def is_stale(self, now_s: float, limit_s: float) -> bool:
        return not self.valid or now_s - self.source_time_s > limit_s


class DeliveryStatus(BaseModel):
    model_config = ConfigDict(frozen=True)

    schema_version: Literal["1.0"] = "1.0"
    mission_id: str | None = None
    request_id: str | None = None
    package_id: str | None = None
    recipient_id: str | None = None
    custody: PackageCustodyState = PackageCustodyState.NOT_MODELED
    receipt_status: ReceiptStatus = ReceiptStatus.NOT_MODELED
    outcome: DeliveryOutcome = DeliveryOutcome.NOT_MODELED
    timeliness: TimelinessOutcome = TimelinessOutcome.NOT_MODELED
    delivery_zone_arrived: bool = False
    landed_at_site: bool = False
    disarmed_at_site: bool = False
    handoff_progress: float = Field(default=0.0, ge=0, le=1)
    deadline_remaining_s: float | None = None
    accepted_at_s: float | None = Field(default=None, ge=0)
    source: str = "not-modeled"


class MissionSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True)

    schema_version: Literal["1.0"] = SCHEMA_VERSION
    run_id: str
    sequence: int = Field(ge=0)
    sim_time_s: float = Field(ge=0)
    recorded_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    mission_state: MissionState
    operator_link_available: CriticalValue
    navigation_confidence: CriticalValue
    energy_margin_wh: CriticalValue
    battery_remaining_pct: float = Field(ge=0, le=100)
    energy_available_wh: float
    energy_recovery_wh: float
    energy_reserve_wh: float
    route_progress: float = Field(ge=0, le=1)
    north_m: float = 0.0
    east_m: float = 0.0
    relative_altitude_m: float = Field(ge=0)
    ground_speed_mps: float = Field(ge=0)
    flight_mode: str = "MISSION"
    vehicle_connected: bool = True
    payload_delivered: bool = False
    delivery: DeliveryStatus = Field(default_factory=DeliveryStatus)
    exploratory: bool = False

    def content_hash(self) -> str:
        data = self.model_dump(mode="json", exclude={"recorded_at"})
        raw = json.dumps(data, sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(raw).hexdigest()


class EngineContext(BaseModel):
    model_config = ConfigDict(frozen=True)

    assurance_state: AssuranceState = AssuranceState.NOMINAL
    recommended_action: RecommendedAction = RecommendedAction.NONE
    decision_code: str = "NOMINAL"
    link_loss_since_s: float | None = None
    healthy_since_s: float | None = None
    terminal_latched: bool = False


class DecisionRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    schema_version: Literal["1.0"] = SCHEMA_VERSION
    run_id: str
    sequence: int
    timestamp_s: float
    prior_state: AssuranceState
    new_state: AssuranceState
    recommended_action: RecommendedAction
    decision_code: str
    summary: str
    trigger_fields: list[str]
    requirement_ids: list[str]
    hazard_ids: list[str]
    rejected_actions: list[RecommendedAction] = Field(default_factory=list)
    input_snapshot_hash: str


class CommandRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    schema_version: Literal["1.0"] = SCHEMA_VERSION
    sequence: int = Field(ge=0)
    command: CommandName
    requested_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    requested_at_s: float = Field(ge=0)
    accepted: bool
    acknowledgement: str
    completed_at_s: float | None = Field(default=None, ge=0)
    decision_sequence: int | None = Field(default=None, ge=0)
    observed_completion_state: str | None = None
    error: str | None = None


class DeliveryEvent(BaseModel):
    model_config = ConfigDict(frozen=True)

    schema_version: Literal["1.0"] = "1.0"
    sequence: int = Field(ge=0)
    sim_time_s: float = Field(ge=0)
    event_type: str
    mission_id: str
    request_id: str
    package_id: str
    recipient_id: str
    source: str
    visible_to_monitor: bool = True
    details: dict[str, Any] = Field(default_factory=dict)


class ScenarioEvent(BaseModel):
    model_config = ConfigDict(frozen=True)

    at_s: float = Field(ge=0)
    set: dict[str, bool | float | str]


class ScenarioExpectation(BaseModel):
    model_config = ConfigDict(frozen=True)

    terminal_state: MissionState
    required_assurance_states: list[AssuranceState] = Field(default_factory=list)
    prohibited_actions: list[RecommendedAction] = Field(default_factory=list)
    required_decision_codes: list[str] = Field(default_factory=list)
    transition_deadline_s: float | None = None
    aircraft_outcome: AircraftOutcome | None = None
    delivery_outcome: DeliveryOutcome | None = None
    timeliness: TimelinessOutcome | None = None


class TraceLinks(BaseModel):
    model_config = ConfigDict(frozen=True)

    requirements: list[str]
    hazards: list[str]


class ScenarioDefinition(BaseModel):
    model_config = ConfigDict(frozen=True)

    schema_version: Literal["1.0"] = SCHEMA_VERSION
    id: str = Field(pattern=r"^T-\d{2}$")
    name: str
    seed: int = 0
    mission: str = "baseline_medical_resupply"
    duration_s: float = Field(default=65, gt=0)
    tick_s: float = Field(default=0.5, gt=0)
    events: list[ScenarioEvent] = Field(default_factory=list)
    expect: ScenarioExpectation
    trace: TraceLinks
    replay_of: str | None = None

    @model_validator(mode="after")
    def events_are_ordered_and_bounded(self) -> ScenarioDefinition:
        times = [event.at_s for event in self.events]
        if times != sorted(times):
            raise ValueError("scenario events must be ordered by at_s")
        if any(at_s > self.duration_s for at_s in times):
            raise ValueError("scenario event occurs after duration_s")
        return self


class AssertionResult(BaseModel):
    name: str
    passed: bool
    expected: str
    observed: str


class EvidenceManifest(BaseModel):
    schema_version: Literal["1.0"] = SCHEMA_VERSION
    run_id: str
    scenario_id: str
    exploratory: bool
    verification_status: VerificationState
    scenario_sha256: str
    configuration_sha256: str
    software_versions: dict[str, str]
    files: dict[str, str]
    artifact_sha256: dict[str, str] = Field(default_factory=dict)
    assertions: list[AssertionResult]


class StreamEnvelope(BaseModel):
    schema_version: Literal["1.0"] = SCHEMA_VERSION
    message_type: Literal["snapshot", "decision", "verification", "status"]
    run_id: str
    sequence: int
    sim_time_s: float
    recorded_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    payload: dict[str, Any]
