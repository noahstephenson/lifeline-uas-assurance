from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from lifeline.config import PROJECT_ROOT, load_config, validate_sitl_qualification
from lifeline.scenarios import load_scenarios


def validate_project(root: Path | None = None) -> dict[str, Any]:
    root = root or PROJECT_ROOT
    errors: list[str] = []
    load_config(root / "config" / "baseline.yaml")
    if root == PROJECT_ROOT:
        validate_sitl_qualification(root / "config" / "sitl-qualification.yaml")
    scenarios = load_scenarios(root / "scenarios")

    requirements = _read_ids(root / "requirements" / "system-requirements.csv", errors)
    hazards = _read_ids(root / "requirements" / "hazards.csv", errors)
    trace_rows = _read_csv(root / "requirements" / "traceability.csv")
    scenario_ids = {scenario.id for scenario in scenarios}

    for row in trace_rows:
        requirement = row.get("requirement_id", "")
        if requirement not in requirements:
            errors.append(f"traceability references unknown requirement {requirement}")
        for test_id in _split(row.get("test_ids", "")):
            if test_id not in scenario_ids:
                errors.append(f"traceability references unknown scenario {test_id}")
        for hazard in _split(row.get("hazard_ids", "")):
            if hazard not in hazards:
                errors.append(f"traceability references unknown hazard {hazard}")

    traced_requirements = {row.get("requirement_id", "") for row in trace_rows}
    for missing in sorted(requirements - traced_requirements):
        errors.append(f"requirement has no traceability row: {missing}")

    for scenario in scenarios:
        for requirement in scenario.trace.requirements:
            if requirement not in requirements:
                errors.append(f"{scenario.id} references unknown requirement {requirement}")
        for hazard in scenario.trace.hazards:
            if hazard not in hazards:
                errors.append(f"{scenario.id} references unknown hazard {hazard}")

    return {
        "valid": not errors,
        "errors": errors,
        "counts": {
            "requirements": len(requirements),
            "hazards": len(hazards),
            "scenarios": len(scenarios),
            "traceability_rows": len(trace_rows),
        },
    }


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def _read_ids(path: Path, errors: list[str]) -> set[str]:
    rows = _read_csv(path)
    ids = [row.get("id", "") for row in rows]
    if len(ids) != len(set(ids)):
        errors.append(f"duplicate IDs in {path.name}")
    if any(not item for item in ids):
        errors.append(f"blank ID in {path.name}")
    return set(ids)


def _split(value: str) -> list[str]:
    return [item.strip() for item in value.split(";") if item.strip()]
