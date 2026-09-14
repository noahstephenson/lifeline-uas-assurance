from __future__ import annotations

from dataclasses import dataclass

from lifeline.config import LifelineConfig
from lifeline.models import (
    AssuranceState,
    DecisionRecord,
    EngineContext,
    MissionSnapshot,
    MissionState,
    RecommendedAction,
)


@dataclass(frozen=True)
class _Decision:
    state: AssuranceState
    action: RecommendedAction
    code: str
    summary: str
    triggers: list[str]
    requirements: list[str]
    hazards: list[str]
    rejected: list[RecommendedAction]


class AssuranceEngine:
    """Pure deterministic assurance policy with no adapter or filesystem dependencies."""

    def __init__(self, config: LifelineConfig):
        self.config = config

    def evaluate(self, snapshot: MissionSnapshot, context: EngineContext) -> tuple[DecisionRecord, EngineContext]:
        now = snapshot.sim_time_s
        link_stale = snapshot.operator_link_available.is_stale(now, self.config.freshness_s.operator_link_available)
        nav_stale = snapshot.navigation_confidence.is_stale(now, self.config.freshness_s.navigation_confidence)
        energy_stale = snapshot.energy_margin_wh.is_stale(now, self.config.freshness_s.energy_margin_wh)

        link_loss_since = context.link_loss_since_s
        healthy_since = context.healthy_since_s

        if context.terminal_latched:
            decision = _Decision(
                AssuranceState.TERMINATE,
                RecommendedAction.CONTROLLED_LAND,
                "TERMINAL_LATCHED",
                "The terminal response remains latched for this run.",
                [],
                ["A-07"],
                ["H-06"],
                [RecommendedAction.CONTINUE, RecommendedAction.RETURN],
            )
        elif link_stale or nav_stale or energy_stale or not snapshot.vehicle_connected:
            missing = []
            if link_stale:
                missing.append("operator_link_available")
            if nav_stale:
                missing.append("navigation_confidence")
            if energy_stale:
                missing.append("energy_margin_wh")
            if not snapshot.vehicle_connected:
                missing.append("vehicle_connected")
            action = (
                RecommendedAction.ABORT_RUN
                if snapshot.mission_state in {MissionState.INITIALIZING, MissionState.PREFLIGHT}
                else RecommendedAction.CONTROLLED_LAND
            )
            decision = _Decision(
                AssuranceState.UNKNOWN,
                action,
                "CRITICAL_INPUT_UNKNOWN",
                "Critical mission data is stale, invalid, or unavailable; healthy operation cannot be assumed.",
                missing,
                ["HM-03", "A-02"],
                ["H-07"],
                [RecommendedAction.CONTINUE, RecommendedAction.RETURN],
            )
        elif float(snapshot.energy_margin_wh.value) <= self.config.energy.critical_margin_wh:
            decision = _Decision(
                AssuranceState.TERMINATE,
                RecommendedAction.CONTROLLED_LAND,
                "ENERGY_CRITICAL",
                "Modeled energy margin reached the critical boundary; controlled landing is required.",
                ["energy_margin_wh"],
                ["A-02", "A-04"],
                ["H-03", "H-04"],
                [RecommendedAction.CONTINUE, RecommendedAction.RETURN],
            )
        elif float(snapshot.navigation_confidence.value) < self.config.navigation.invalid_below:
            decision = _Decision(
                AssuranceState.TERMINATE,
                RecommendedAction.CONTROLLED_LAND,
                "NAVIGATION_INVALID",
                "Return was inhibited because navigation confidence is below the approved threshold.",
                ["navigation_confidence"],
                ["A-02", "A-03", "A-08"],
                ["H-02", "H-04"],
                [RecommendedAction.CONTINUE, RecommendedAction.RETURN],
            )
        elif float(snapshot.energy_margin_wh.value) <= (
            self.config.energy.usable_capacity_wh * self.config.energy.recovery_margin_fraction
        ):
            decision = _Decision(
                AssuranceState.RECOVER,
                RecommendedAction.RETURN,
                "ENERGY_RECOVERY_REQUIRED",
                "Modeled energy margin entered the recovery band while navigation remains valid.",
                ["energy_margin_wh", "navigation_confidence"],
                ["A-02", "A-04"],
                ["H-03", "H-04"],
                [RecommendedAction.CONTINUE],
            )
        elif not bool(snapshot.operator_link_available.value):
            link_loss_since = now if link_loss_since is None else link_loss_since
            healthy_since = None
            if now - link_loss_since < self.config.link_activation_dwell_s:
                decision = _Decision(
                    AssuranceState.WATCH,
                    RecommendedAction.NONE,
                    "LINK_LOSS_DWELL",
                    "Operator-link interruption is being observed during the activation dwell.",
                    ["operator_link_available"],
                    ["HM-04", "A-05"],
                    ["H-01", "H-05"],
                    [RecommendedAction.RETURN, RecommendedAction.CONTROLLED_LAND],
                )
            elif snapshot.mission_state == MissionState.OUTBOUND and not snapshot.payload_delivered:
                decision = _Decision(
                    AssuranceState.DEGRADED,
                    RecommendedAction.CONTINUE,
                    "LINK_LOSS_CONTINUE_OUTBOUND",
                    "The sustained link loss is tolerated because navigation and energy remain supportable before delivery.",
                    ["operator_link_available", "mission_state"],
                    ["A-06", "A-08"],
                    ["H-01"],
                    [RecommendedAction.RETURN, RecommendedAction.CONTROLLED_LAND],
                )
            else:
                decision = _Decision(
                    AssuranceState.RECOVER,
                    RecommendedAction.RETURN,
                    "LINK_LOSS_RETURN_AFTER_DELIVERY",
                    "The sustained link loss occurred after delivery or during recovery; return is selected.",
                    ["operator_link_available", "mission_state"],
                    ["A-06", "A-08"],
                    ["H-01"],
                    [RecommendedAction.CONTINUE],
                )
        elif context.assurance_state in {AssuranceState.WATCH, AssuranceState.DEGRADED}:
            link_loss_since = None
            healthy_since = now if healthy_since is None else healthy_since
            if now - healthy_since < self.config.recovery_dwell_s:
                decision = _Decision(
                    AssuranceState.WATCH,
                    RecommendedAction.NONE,
                    "RECOVERY_DWELL",
                    "Healthy inputs are being observed for the required recovery dwell.",
                    ["operator_link_available"],
                    ["A-07"],
                    ["H-05", "H-06"],
                    [],
                )
            else:
                decision = self._nominal()
                healthy_since = None
        else:
            link_loss_since = None
            healthy_since = None
            decision = self._nominal()

        terminal_latched = context.terminal_latched or decision.state == AssuranceState.TERMINATE
        new_context = EngineContext(
            assurance_state=decision.state,
            recommended_action=decision.action,
            decision_code=decision.code,
            link_loss_since_s=link_loss_since,
            healthy_since_s=healthy_since,
            terminal_latched=terminal_latched,
        )
        record = DecisionRecord(
            run_id=snapshot.run_id,
            sequence=snapshot.sequence,
            timestamp_s=now,
            prior_state=context.assurance_state,
            new_state=decision.state,
            recommended_action=decision.action,
            decision_code=decision.code,
            summary=decision.summary,
            trigger_fields=decision.triggers,
            requirement_ids=decision.requirements,
            hazard_ids=decision.hazards,
            rejected_actions=decision.rejected,
            input_snapshot_hash=snapshot.content_hash(),
        )
        return record, new_context

    @staticmethod
    def _nominal() -> _Decision:
        return _Decision(
            AssuranceState.NOMINAL,
            RecommendedAction.NONE,
            "NOMINAL",
            "All monitored resources are within the configured simulation envelope.",
            [],
            ["A-01"],
            [],
            [],
        )
