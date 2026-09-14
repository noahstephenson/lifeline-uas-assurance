from lifeline.assurance import AssuranceEngine
from lifeline.config import load_config
from lifeline.models import (
    AssuranceState,
    CriticalValue,
    EngineContext,
    MissionSnapshot,
    MissionState,
    RecommendedAction,
)


def snapshot(
    *,
    time: float = 10.0,
    link: bool = True,
    nav: float = 0.9,
    energy: float = 20.0,
    state: MissionState = MissionState.OUTBOUND,
    source_time: float | None = None,
) -> MissionSnapshot:
    source_time = time if source_time is None else source_time

    def value(item, source):
        return CriticalValue(
            value=item,
            source_time_s=source_time,
            receipt_time_s=time,
            source=source,
        )

    return MissionSnapshot(
        run_id="test",
        sequence=int(time * 2),
        sim_time_s=time,
        mission_state=state,
        operator_link_available=value(link, "test"),
        navigation_confidence=value(nav, "test"),
        energy_margin_wh=value(energy, "test"),
        battery_remaining_pct=70,
        energy_available_wh=60,
        energy_recovery_wh=20,
        energy_reserve_wh=20,
        route_progress=0.3,
        relative_altitude_m=25,
        ground_speed_mps=8,
    )


def test_navigation_invalid_inhibits_return():
    record, context = AssuranceEngine(load_config()).evaluate(snapshot(nav=0.25), EngineContext())
    assert context.assurance_state == AssuranceState.TERMINATE
    assert record.recommended_action == RecommendedAction.CONTROLLED_LAND
    assert RecommendedAction.RETURN in record.rejected_actions


def test_link_loss_observes_dwell_then_continues_outbound():
    engine = AssuranceEngine(load_config())
    first, context = engine.evaluate(snapshot(time=10, link=False), EngineContext())
    second, context = engine.evaluate(snapshot(time=13, link=False), context)
    assert first.new_state == AssuranceState.WATCH
    assert second.new_state == AssuranceState.DEGRADED
    assert second.recommended_action == RecommendedAction.CONTINUE


def test_terminal_decision_is_latched():
    engine = AssuranceEngine(load_config())
    _, context = engine.evaluate(snapshot(nav=0.2), EngineContext())
    recovered, _ = engine.evaluate(snapshot(time=11, nav=0.9), context)
    assert recovered.decision_code == "TERMINAL_LATCHED"
    assert recovered.new_state == AssuranceState.TERMINATE


def test_stale_input_is_unknown():
    record, _ = AssuranceEngine(load_config()).evaluate(snapshot(time=10, source_time=0), EngineContext())
    assert record.new_state == AssuranceState.UNKNOWN
    assert record.recommended_action == RecommendedAction.CONTROLLED_LAND
