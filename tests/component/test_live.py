import asyncio

import pytest

from lifeline.config import validate_sitl_qualification
from lifeline.evidence import verify_run_integrity
from lifeline.live import LiveSession, LiveStatus
from lifeline.scenarios import load_scenario, run_scenario
from lifeline.scenarios.runner import ScenarioRun


def test_live_session_holds_for_dashboard_and_reconnects_without_duplicates(monkeypatch, tmp_path):
    async def exercise():
        scenario = load_scenario("T-01")
        config = validate_sitl_qualification()

        async def fake_px4(*_args, **kwargs):
            await kwargs["on_ready"](kwargs["run_id"])
            await kwargs["start_gate"].wait()
            base = run_scenario(scenario, config, run_id=kwargs["run_id"])
            active = base.decisions[0]
            for snapshot in base.snapshots[:4]:
                matching = next((item for item in base.decisions if item.sequence == snapshot.sequence), None)
                active = matching or active
                await kwargs["on_snapshot"](snapshot, active)
            return ScenarioRun(
                run_id=base.run_id,
                scenario=base.scenario,
                snapshots=base.snapshots[:4],
                decisions=base.decisions,
                assertions=base.assertions,
                source="px4",
                configuration=config,
                environment={"vehicle_uuid": "4242"},
            )

        monkeypatch.setattr("lifeline.live.run_px4_scenario", fake_px4)
        session = LiveSession(scenario, config, run_id="LIVE-ORDERING", start_token="one-time", evidence_root=tmp_path)
        session.launch()
        for _ in range(50):
            if session.status == LiveStatus.READY:
                break
            await asyncio.sleep(0.01)
        assert session.status == LiveStatus.READY
        with pytest.raises(RuntimeError, match="dashboard"):
            session.release("one-time")
        buffered, first_queue = await session.subscribe(-1)
        assert buffered == []
        with pytest.raises(PermissionError):
            session.release("wrong")
        session.release("one-time")
        await session._task
        assert session.status == LiveStatus.COMPLETE
        await session.unsubscribe(first_queue)
        buffered, second_queue = await session.subscribe(1)
        assert [item["sequence"] for item in buffered] == [2, 3]
        assert second_queue.empty()
        await session.unsubscribe(second_queue)
        integrity = verify_run_integrity("LIVE-ORDERING", tmp_path)
        assert not integrity["complete"]
        assert integrity["missing"] == ["api.log", "px4.log"]

    asyncio.run(exercise())


def test_live_connection_failure_finalizes_error_evidence(monkeypatch, tmp_path):
    async def exercise():
        async def failed_px4(*_args, **_kwargs):
            raise ConnectionError("simulator unavailable")

        monkeypatch.setattr("lifeline.live.run_px4_scenario", failed_px4)
        session = LiveSession(
            load_scenario("T-01"),
            validate_sitl_qualification(),
            run_id="LIVE-ERROR",
            start_token="one-time",
            evidence_root=tmp_path,
        )
        session.launch()
        await session._task
        assert session.status == LiveStatus.ERROR
        integrity = verify_run_integrity("LIVE-ERROR", tmp_path)
        assert integrity["verification_status"] == "INCOMPLETE"
        assert (tmp_path / "LIVE-ERROR" / "run-summary.json").read_text(encoding="utf-8").find('"ERROR"') > 0

    asyncio.run(exercise())
