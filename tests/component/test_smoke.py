import asyncio
import json

from lifeline.config import validate_sitl_qualification
from lifeline.evidence import verify_run_integrity
from lifeline.smoke import finalize_smoke_setup_error, run_px4_smoke


class FailedAdapter:
    def __init__(self, config, *, allow_sitl_actions=False):
        self.vehicle_uuid = None

    async def connect(self):
        raise ConnectionError("PX4 is not listening")


def test_smoke_connection_failure_leaves_error_bundle(tmp_path):
    manifest = asyncio.run(
        run_px4_smoke(
            validate_sitl_qualification(),
            run_id="SMOKE-ERROR",
            output_root=tmp_path,
            adapter_factory=FailedAdapter,
        )
    )
    assert manifest["verification_status"] == "ERROR"
    summary = json.loads((tmp_path / "SMOKE-ERROR" / "smoke-summary.json").read_text(encoding="utf-8"))
    assert "PX4 is not listening" in summary["error"]
    integrity = verify_run_integrity("SMOKE-ERROR", tmp_path)
    assert integrity["verification_status"] == "INCOMPLETE"
    assert integrity["missing"] == ["px4.log"]


class HangingAdapter:
    def __init__(self, config, *, allow_sitl_actions=False):
        self.vehicle_uuid = None

    async def connect(self):
        await asyncio.sleep(60)


def test_smoke_connection_timeout_leaves_error_bundle(tmp_path):
    manifest = asyncio.run(
        run_px4_smoke(
            validate_sitl_qualification(),
            run_id="SMOKE-TIMEOUT",
            output_root=tmp_path,
            adapter_factory=HangingAdapter,
            connect_timeout_s=0.01,
        )
    )
    assert manifest["verification_status"] == "ERROR"
    summary = json.loads((tmp_path / "SMOKE-TIMEOUT" / "smoke-summary.json").read_text(encoding="utf-8"))
    assert "TimeoutError" in summary["error"]


def test_smoke_setup_failure_finalizes_existing_reserved_directory(tmp_path):
    run_dir = tmp_path / "SMOKE-SETUP"
    run_dir.mkdir()
    manifest = finalize_smoke_setup_error(
        validate_sitl_qualification(),
        run_id="SMOKE-SETUP",
        error="PX4 target missing",
        output_root=tmp_path,
    )
    assert manifest["verification_status"] == "ERROR"
    assert (run_dir / "manifest.json").is_file()
    integrity = verify_run_integrity("SMOKE-SETUP", tmp_path)
    assert integrity["missing"] == ["px4.log"]
