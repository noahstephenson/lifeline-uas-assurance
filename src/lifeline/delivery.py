from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field

from lifeline.config import PROJECT_ROOT
from lifeline.models import (
    DeliveryEvent,
    DeliveryOutcome,
    DeliveryStatus,
    PackageCustodyState,
    ReceiptStatus,
    TimelinessOutcome,
)


class StationDefinition(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    name: str


class ManifestItem(BaseModel):
    model_config = ConfigDict(frozen=True)

    item_id: str
    description: str
    quantity: int = Field(gt=0)
    unit: str


class PackageDefinition(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    description: str
    mass_kg: float = Field(gt=0)
    mass_basis: str
    sealed: bool
    cold_chain_required: bool
    manifest: list[ManifestItem]


class DeliveryZone(BaseModel):
    model_config = ConfigDict(frozen=True)

    frame: str
    north_m: float
    east_m: float
    radius_m: float = Field(gt=0)


class HandoffDefinition(BaseModel):
    model_config = ConfigDict(frozen=True)

    method: str
    required_landed: bool
    required_disarmed: bool
    unloading_dwell_s: float = Field(ge=0)


class AcceptanceDefinition(BaseModel):
    model_config = ConfigDict(frozen=True)

    require_request_match: bool
    require_package_match: bool
    require_recipient_match: bool
    require_sealed_package: bool


class MissionContract(BaseModel):
    model_config = ConfigDict(frozen=True)

    schema_version: str
    mission_id: str
    request_id: str
    origin: StationDefinition
    recipient: StationDefinition
    package: PackageDefinition
    dispatch_time_s: float = Field(ge=0)
    delivery_deadline_s: float = Field(gt=0)
    deadline_basis: str
    delivery_zone: DeliveryZone
    handoff: HandoffDefinition
    acceptance: AcceptanceDefinition


def load_mission_contract(path: Path | None = None) -> MissionContract:
    mission_path = path or PROJECT_ROOT / "config" / "missions" / "medical-resupply.yaml"
    raw = yaml.safe_load(mission_path.read_text(encoding="utf-8"))
    return MissionContract.model_validate(raw["contract"])


class DeliveryThread:
    """Deterministic request-to-receipt state owned by Lifeline, not PX4."""

    def __init__(self, contract: MissionContract) -> None:
        self.contract = contract
        self.events: list[DeliveryEvent] = []
        self._event_sequence = 0
        self._arrived_at_s: float | None = None
        self._handoff_started_at_s: float | None = None
        self._landing_observed = False
        self._disarm_observed = False
        self._unloading_completed = False
        self._accepted_at_s: float | None = None
        self._receipt_emitted = False
        self._seen_receipts: set[str] = set()
        self._status = DeliveryStatus(
            mission_id=contract.mission_id,
            request_id=contract.request_id,
            package_id=contract.package.id,
            recipient_id=contract.recipient.id,
            custody=PackageCustodyState.LOGISTICS_POINT,
            receipt_status=ReceiptStatus.PENDING,
            outcome=DeliveryOutcome.PENDING,
            timeliness=TimelinessOutcome.PENDING,
            deadline_remaining_s=contract.delivery_deadline_s,
            source="modeled-receiving-station",
        )
        self._emit(0.0, "REQUEST_ACCEPTED", {"origin": contract.origin.id})
        self._emit(0.0, "PACKAGE_ASSIGNED", {"mass_kg": contract.package.mass_kg})

    @property
    def status(self) -> DeliveryStatus:
        return self._status

    def update(
        self,
        *,
        sim_time_s: float,
        dispatched: bool,
        at_delivery_zone: bool,
        landed: bool,
        disarmed: bool,
        terminal: bool,
        response_mode: str = "accepted",
        deadline_s: float | None = None,
        response_delay_s: float = 6.0,
        aircraft_observation_source: str = "deterministic-fake-telemetry",
    ) -> DeliveryStatus:
        deadline = float(deadline_s if deadline_s is not None else self.contract.delivery_deadline_s)
        custody = self._status.custody
        receipt = self._status.receipt_status
        outcome = self._status.outcome
        timeliness = self._status.timeliness
        handoff_progress = self._status.handoff_progress

        if dispatched and custody == PackageCustodyState.LOGISTICS_POINT:
            custody = PackageCustodyState.AIRCRAFT
            self._emit(sim_time_s, "PACKAGE_LOADED", {"aircraft_source": "simulation"})

        if at_delivery_zone and self._arrived_at_s is None:
            self._arrived_at_s = sim_time_s
            self._emit(
                sim_time_s,
                "DELIVERY_ZONE_ARRIVAL",
                {"landed": landed, "disarmed": disarmed},
                source=aircraft_observation_source,
            )

        if self._arrived_at_s is not None and landed and not self._landing_observed:
            self._landing_observed = True
            self._emit(sim_time_s, "LANDING_OBSERVED", {}, source=aircraft_observation_source)
        if self._arrived_at_s is not None and disarmed and not self._disarm_observed:
            self._disarm_observed = True
            self._emit(sim_time_s, "DISARM_OBSERVED", {}, source=aircraft_observation_source)

        conditions_met = (
            self._arrived_at_s is not None
            and (self._landing_observed or not self.contract.handoff.required_landed)
            and (self._disarm_observed or not self.contract.handoff.required_disarmed)
        )
        if conditions_met and self._handoff_started_at_s is None:
            self._handoff_started_at_s = sim_time_s
            self._emit(
                sim_time_s,
                "UNLOADING_STARTED",
                {"required_dwell_s": self.contract.handoff.unloading_dwell_s},
            )

        if self._handoff_started_at_s is not None and outcome == DeliveryOutcome.PENDING:
            elapsed = max(0.0, sim_time_s - self._handoff_started_at_s)
            handoff_progress = min(1.0, elapsed / max(self.contract.handoff.unloading_dwell_s, 0.001))
            if handoff_progress >= 1.0:
                if not self._unloading_completed:
                    self._unloading_completed = True
                    self._emit(sim_time_s, "UNLOADING_COMPLETE", {})
                receipt_id = f"RCPT-{self.contract.request_id}"
                ready_at = self._handoff_started_at_s + self.contract.handoff.unloading_dwell_s
                if response_mode == "delayed" and sim_time_s < ready_at + response_delay_s:
                    receipt = ReceiptStatus.PENDING
                elif response_mode == "absent":
                    receipt = ReceiptStatus.ABSENT
                    custody = PackageCustodyState.RECEIVING_STATION
                    outcome = DeliveryOutcome.UNCONFIRMED
                    timeliness = TimelinessOutcome.UNKNOWN
                    self._emit_once(sim_time_s, "RECEIPT_ABSENT", {})
                elif response_mode == "malformed":
                    receipt = ReceiptStatus.MALFORMED
                    custody = PackageCustodyState.RECEIVING_STATION
                    outcome = DeliveryOutcome.UNCONFIRMED
                    timeliness = TimelinessOutcome.UNKNOWN
                    self._emit_once(sim_time_s, "RECEIPT_MALFORMED", {})
                elif response_mode in {"wrong_package", "wrong_request", "wrong_recipient", "rejected"}:
                    receipt = ReceiptStatus.REJECTED
                    outcome = DeliveryOutcome.REJECTED
                    timeliness = TimelinessOutcome.UNKNOWN
                    self._emit_once(sim_time_s, "RECEIPT_REJECTED", {"reason": response_mode})
                else:
                    accepted = self.ingest_receipt(
                        receipt_id=receipt_id,
                        mission_id=self.contract.mission_id,
                        request_id=self.contract.request_id,
                        package_id=self.contract.package.id,
                        recipient_id=self.contract.recipient.id,
                        sim_time_s=sim_time_s,
                    )
                    receipt = ReceiptStatus.ACCEPTED if accepted else ReceiptStatus.DUPLICATE
                    custody = PackageCustodyState.RECEIVING_STATION
                    outcome = DeliveryOutcome.ACCEPTED
                    self._accepted_at_s = self._accepted_at_s or sim_time_s
                    timeliness = TimelinessOutcome.ON_TIME if self._accepted_at_s <= deadline else TimelinessOutcome.LATE

        if terminal and outcome == DeliveryOutcome.PENDING:
            outcome = DeliveryOutcome.NOT_COMPLETED
            timeliness = TimelinessOutcome.UNKNOWN
            self._emit_once(sim_time_s, "DELIVERY_NOT_COMPLETED", {})

        self._status = DeliveryStatus(
            mission_id=self.contract.mission_id,
            request_id=self.contract.request_id,
            package_id=self.contract.package.id,
            recipient_id=self.contract.recipient.id,
            custody=custody,
            receipt_status=receipt,
            outcome=outcome,
            timeliness=timeliness,
            delivery_zone_arrived=self._arrived_at_s is not None,
            landed_at_site=self._landing_observed,
            disarmed_at_site=self._disarm_observed,
            handoff_progress=handoff_progress,
            deadline_remaining_s=deadline - sim_time_s,
            accepted_at_s=self._accepted_at_s,
            source="modeled-receiving-station",
        )
        return self._status

    def ingest_receipt(
        self,
        *,
        receipt_id: str,
        mission_id: str,
        request_id: str,
        package_id: str,
        recipient_id: str,
        sim_time_s: float,
    ) -> bool:
        if receipt_id in self._seen_receipts:
            self._emit(sim_time_s, "RECEIPT_DUPLICATE", {"receipt_id": receipt_id})
            return False
        self._seen_receipts.add(receipt_id)
        matches = (
            mission_id == self.contract.mission_id
            and request_id == self.contract.request_id
            and package_id == self.contract.package.id
            and recipient_id == self.contract.recipient.id
        )
        if not matches:
            self._emit(sim_time_s, "RECEIPT_REJECTED", {"receipt_id": receipt_id, "reason": "identifier_mismatch"})
            return False
        self._emit(sim_time_s, "RECEIPT_ACCEPTED", {"receipt_id": receipt_id})
        return True

    def _emit_once(self, sim_time_s: float, event_type: str, details: dict[str, Any]) -> None:
        if self._receipt_emitted:
            return
        self._receipt_emitted = True
        self._emit(sim_time_s, event_type, details)

    def _emit(
        self,
        sim_time_s: float,
        event_type: str,
        details: dict[str, Any],
        *,
        source: str = "modeled-receiving-station",
    ) -> None:
        self.events.append(
            DeliveryEvent(
                sequence=self._event_sequence,
                sim_time_s=sim_time_s,
                event_type=event_type,
                mission_id=self.contract.mission_id,
                request_id=self.contract.request_id,
                package_id=self.contract.package.id,
                recipient_id=self.contract.recipient.id,
                source=source,
                details=details,
            )
        )
        self._event_sequence += 1
