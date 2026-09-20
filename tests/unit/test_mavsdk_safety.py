import asyncio

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
