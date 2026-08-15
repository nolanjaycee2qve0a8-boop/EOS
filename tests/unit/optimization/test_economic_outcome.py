"""Focused accounting-contract tests for TASK-163 economic outcome evidence."""

import ast
import inspect
from dataclasses import FrozenInstanceError, fields
from pathlib import Path
from typing import Any, cast

import pytest

import optimization
from optimization import (
    BatteryOptimizationModel,
    DeterministicEconomicOutcomeCalculator,
    DeterministicTerminalEnergyValueCalculator,
    EconomicOutcomeBoundary,
    EconomicOutcomeEvidence,
    EconomicOutcomeInput,
    TerminalEnergyValueEvidence,
    TerminalEnergyValueInput,
)


def _terminal_evidence(
    terminal_soc: float = 0.80,
    valuation_import_price: float = 0.90,
) -> TerminalEnergyValueEvidence:
    model = BatteryOptimizationModel(10.0, 0.20, 1.0, 3.0, 3.0, 0.95, 0.95)
    return DeterministicTerminalEnergyValueCalculator().calculate(
        TerminalEnergyValueInput(terminal_soc, model, valuation_import_price)
    )


def _calculate(
    realized_import_cost: float,
    evidence: TerminalEnergyValueEvidence,
) -> EconomicOutcomeEvidence:
    return DeterministicEconomicOutcomeCalculator().calculate(
        EconomicOutcomeInput(realized_import_cost, evidence)
    )


def test_contracts_are_frozen_slotted_and_preserve_exact_evidence_identity() -> None:
    terminal_evidence = _terminal_evidence()
    outcome_input = EconomicOutcomeInput(10.0, terminal_evidence)
    outcome = DeterministicEconomicOutcomeCalculator().calculate(outcome_input)

    assert [field.name for field in fields(EconomicOutcomeInput)] == [
        "realized_import_cost",
        "terminal_energy_value_evidence",
    ]
    assert [field.name for field in fields(EconomicOutcomeEvidence)] == [
        "source_input",
        "realized_import_cost",
        "terminal_energy_value_evidence",
        "terminal_energy_value",
        "net_economic_cost",
        "terminal_value_credit_applied",
    ]
    assert outcome.source_input is outcome_input
    assert outcome.terminal_energy_value_evidence is terminal_evidence
    assert outcome.terminal_energy_value == terminal_evidence.terminal_energy_value
    assert not hasattr(outcome_input, "__dict__")
    assert not hasattr(outcome, "__dict__")
    with pytest.raises(FrozenInstanceError):
        cast(Any, outcome_input).realized_import_cost = 2.0


def test_basic_subtraction_formula_credits_terminal_value() -> None:
    outcome = _calculate(
        10.0, _terminal_evidence(terminal_soc=0.60, valuation_import_price=0.75)
    )

    assert outcome.terminal_energy_value == pytest.approx(2.85)
    assert outcome.net_economic_cost == pytest.approx(7.15)
    assert outcome.terminal_value_credit_applied is True


def test_zero_terminal_value_equals_realized_cost() -> None:
    outcome = _calculate(10.0, _terminal_evidence(terminal_soc=0.20))

    assert outcome.terminal_energy_value == 0.0
    assert outcome.net_economic_cost == 10.0
    assert outcome.terminal_value_credit_applied is False


def test_terminal_value_can_exceed_realized_cost_and_produce_negative_net_cost() -> (
    None
):
    outcome = _calculate(2.0, _terminal_evidence())

    assert outcome.terminal_energy_value == pytest.approx(5.13)
    assert outcome.net_economic_cost == pytest.approx(-3.13)


def test_zero_realized_import_cost_is_valid() -> None:
    outcome = _calculate(0.0, _terminal_evidence())

    assert outcome.net_economic_cost == pytest.approx(-5.13)


@pytest.mark.parametrize(
    ("realized_import_cost", "exception"),
    (
        (-0.01, ValueError),
        (float("nan"), ValueError),
        (float("inf"), ValueError),
        (True, TypeError),
        (cast(Any, "10"), TypeError),
    ),
)
def test_input_rejects_invalid_realized_import_cost(
    realized_import_cost: object,
    exception: type[Exception],
) -> None:
    with pytest.raises(exception):
        EconomicOutcomeInput(cast(Any, realized_import_cost), _terminal_evidence())


def test_result_rejects_reconstructed_terminal_evidence_and_recomputed_values() -> None:
    terminal_evidence = _terminal_evidence()
    outcome_input = EconomicOutcomeInput(10.0, terminal_evidence)
    reconstructed = _terminal_evidence()

    with pytest.raises(ValueError, match="exact source identity"):
        EconomicOutcomeEvidence(
            outcome_input,
            10.0,
            reconstructed,
            reconstructed.terminal_energy_value,
            10.0 - reconstructed.terminal_energy_value,
            True,
        )
    with pytest.raises(ValueError, match="terminal_energy_value"):
        EconomicOutcomeEvidence(
            outcome_input,
            10.0,
            terminal_evidence,
            1.0,
            9.0,
            True,
        )


def test_higher_import_cost_can_have_lower_net_economic_cost() -> None:
    path_a = _calculate(
        8.0, _terminal_evidence(terminal_soc=0.30, valuation_import_price=0.90)
    )
    path_b = _calculate(
        8.5, _terminal_evidence(terminal_soc=0.80, valuation_import_price=0.90)
    )

    assert path_b.realized_import_cost > path_a.realized_import_cost
    assert path_b.net_economic_cost < path_a.net_economic_cost


def test_boundary_is_abstract_stateless_and_explicit() -> None:
    signature = inspect.signature(EconomicOutcomeBoundary.calculate)

    assert inspect.isabstract(EconomicOutcomeBoundary)
    assert EconomicOutcomeBoundary.__slots__ == ()
    assert DeterministicEconomicOutcomeCalculator.__slots__ == ()
    assert list(signature.parameters) == ["self", "outcome_input"]
    with pytest.raises(TypeError):
        cast(Any, EconomicOutcomeBoundary)()
    assert not hasattr(DeterministicEconomicOutcomeCalculator(), "__dict__")


def test_public_api_and_dependency_isolation() -> None:
    assert {
        "EconomicOutcomeInput",
        "EconomicOutcomeEvidence",
        "EconomicOutcomeBoundary",
        "DeterministicEconomicOutcomeCalculator",
    } <= set(optimization.__all__)

    source = Path("optimization/economic_outcome.py").read_text(encoding="utf-8")
    imports = {
        alias.name
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {
        node.module or ""
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.ImportFrom)
    }
    forbidden = (
        "forecast",
        "ems_strategy",
        "ems_simulator",
        "simulator",
        "optimization.economic_planning",
        "optimization.economic_grid_charge_value",
        "optimization.economic_multi_opportunity_candidate_planning",
    )
    assert not any(
        name == prefix or name.startswith(f"{prefix}.")
        for name in imports
        for prefix in forbidden
    )
