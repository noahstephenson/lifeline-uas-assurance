from __future__ import annotations

from pathlib import Path

import yaml

from lifeline.config import PROJECT_ROOT
from lifeline.models import ScenarioDefinition


def load_scenarios(directory: Path | None = None) -> list[ScenarioDefinition]:
    scenario_dir = directory or PROJECT_ROOT / "scenarios"
    return [
        ScenarioDefinition.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
        for path in sorted(scenario_dir.glob("T-*.yaml"))
    ]


def scenario_path(scenario_id: str, directory: Path | None = None) -> Path:
    scenario_dir = directory or PROJECT_ROOT / "scenarios"
    matches = list(scenario_dir.glob(f"{scenario_id}-*.yaml"))
    if len(matches) != 1:
        raise ValueError(f"expected one scenario matching {scenario_id}, found {len(matches)}")
    return matches[0]


def load_scenario(scenario_id: str, directory: Path | None = None) -> ScenarioDefinition:
    path = scenario_path(scenario_id, directory)
    return ScenarioDefinition.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
