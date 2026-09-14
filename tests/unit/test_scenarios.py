import pytest

from lifeline.config import load_config
from lifeline.scenarios import load_scenarios, run_scenario


@pytest.mark.parametrize("scenario", load_scenarios(), ids=lambda scenario: scenario.id)
def test_controlled_scenario_matches_oracle(scenario):
    run = run_scenario(scenario, load_config(), run_id=f"TEST-{scenario.id}")
    failures = [result.model_dump() for result in run.assertions if not result.passed]
    assert not failures
