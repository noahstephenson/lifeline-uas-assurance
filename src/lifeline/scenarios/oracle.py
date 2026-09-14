from __future__ import annotations

from lifeline.models import AssertionResult, DecisionRecord, MissionSnapshot, ScenarioDefinition


def evaluate_expectations(
    scenario: ScenarioDefinition,
    snapshots: list[MissionSnapshot],
    decisions: list[DecisionRecord],
) -> list[AssertionResult]:
    terminal = snapshots[-1].mission_state
    states = {record.new_state for record in decisions}
    actions = {record.recommended_action for record in decisions}
    codes = {record.decision_code for record in decisions}

    results = [
        AssertionResult(
            name="terminal_state",
            passed=terminal == scenario.expect.terminal_state,
            expected=scenario.expect.terminal_state.value,
            observed=terminal.value,
        )
    ]
    for state in scenario.expect.required_assurance_states:
        results.append(
            AssertionResult(
                name=f"required_state:{state.value}",
                passed=state in states,
                expected="observed",
                observed="observed" if state in states else "missing",
            )
        )
    for action in scenario.expect.prohibited_actions:
        results.append(
            AssertionResult(
                name=f"prohibited_action:{action.value}",
                passed=action not in actions,
                expected="absent",
                observed="absent" if action not in actions else "observed",
            )
        )
    for code in scenario.expect.required_decision_codes:
        results.append(
            AssertionResult(
                name=f"required_code:{code}",
                passed=code in codes,
                expected="observed",
                observed="observed" if code in codes else "missing",
            )
        )
    if scenario.expect.transition_deadline_s is not None:
        relevant = [
            record.timestamp_s
            for record in decisions
            if record.decision_code in scenario.expect.required_decision_codes and record.decision_code != "NOMINAL"
        ]
        observed = min(relevant) if relevant else None
        results.append(
            AssertionResult(
                name="transition_deadline",
                passed=observed is not None and observed <= scenario.expect.transition_deadline_s,
                expected=f"<= {scenario.expect.transition_deadline_s}",
                observed="missing" if observed is None else str(observed),
            )
        )
    return results
