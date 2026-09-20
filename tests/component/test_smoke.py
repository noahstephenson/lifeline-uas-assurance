import asyncio
import json

from lifeline.config import validate_sitl_qualification
from lifeline.evidence import verify_run_integrity
from lifeline.smoke import run_px4_smoke


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
