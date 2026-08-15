"""Focused accounting-contract tests for TASK-168 extended outcome evidence."""

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
    DeterministicExtendedEconomicOutcomeCalculator,
    DeterministicTerminalEnergyValueCalculator,
    EconomicOutcomeInput,
    ExtendedEconomicOutcomeBoundary,
    ExtendedEconomicOutcomeEvidence,
    ExtendedEconomicOutcomeInput,
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
    realized_import_cost: float = 10.0,
    realized_export_revenue: float = 1.0,
    battery_degradation_cost: float = 0.5,
    terminal_evidence: TerminalEnergyValueEvidence | None = None,
) -> ExtendedEconomicOutcomeEvidence:
    return DeterministicExtendedEconomicOutcomeCalculator().calculate(
        ExtendedEconomicOutcomeInput(
            realized_import_cost,
            realized_export_revenue,
            battery_degradation_cost,
            _terminal_evidence() if terminal_evidence is None else terminal_evidence,
        )
    )


def test_contracts_are_frozen_slotted_and_preserve_exact_evidence_identity() -> None:
    terminal_evidence = _terminal_evidence()
    outcome_input = ExtendedEconomicOutcomeInput(10.0, 1.0, 0.5, terminal_evidence)
    outcome = DeterministicExtendedEconomicOutcomeCalculator().calculate(outcome_input)

    assert [field.name for field in fields(ExtendedEconomicOutcomeInput)] == [
        "realized_import_cost",
        "realized_export_revenue",
        "battery_degradation_cost",
        "terminal_energy_value_evidence",
    ]
    assert [field.name for field in fields(ExtendedEconomicOutcomeEvidence)] == [
        "source_input",
        "realized_import_cost",
        "realized_export_revenue",
        "battery_degradation_cost",
        "terminal_energy_value_evidence",
        "terminal_energy_value",
        "adjusted_net_economic_cost",
    ]
    assert outcome.source_input is outcome_input
    assert outcome.terminal_energy_value_evidence is terminal_evidence
    assert not hasattr(outcome_input, "__dict__")
    assert not hasattr(outcome, "__dict__")
    with pytest.raises(FrozenInstanceError):
        cast(Any, outcome_input).realized_export_revenue = 2.0


def test_formula_aggregates_only_the_supplied_components() -> None:
    outcome = _calculate()

    assert outcome.terminal_energy_value == pytest.approx(5.13)
    assert outcome.adjusted_net_economic_cost == pytest.approx(4.37)


def test_zero_export_revenue_and_degradation_are_valid() -> None:
    outcome = _calculate(10.0, 0.0, 0.0, _terminal_evidence(0.20))

    assert outcome.adjusted_net_economic_cost == 10.0


def test_export_revenue_lowers_and_degradation_cost_raises_adjusted_cost() -> None:
    terminal_evidence = _terminal_evidence(0.20)
    baseline = _calculate(10.0, 0.0, 0.0, terminal_evidence)
    with_export = _calculate(10.0, 2.0, 0.0, terminal_evidence)
    with_degradation = _calculate(10.0, 0.0, 2.0, terminal_evidence)

    assert (
        with_export.adjusted_net_economic_cost
        == baseline.adjusted_net_economic_cost - 2.0
    )
    assert (
        with_degradation.adjusted_net_economic_cost
        == baseline.adjusted_net_economic_cost + 2.0
    )


def test_terminal_value_lowers_adjusted_cost_and_negative_cost_is_valid() -> None:
    no_terminal_value = _calculate(2.0, 0.0, 0.0, _terminal_evidence(0.20))
    with_terminal_value = _calculate(2.0, 0.0, 0.0, _terminal_evidence())

    assert with_terminal_value.adjusted_net_economic_cost < (
        no_terminal_value.adjusted_net_economic_cost
    )
    assert with_terminal_value.adjusted_net_economic_cost == pytest.approx(-3.13)


@pytest.mark.parametrize(
    ("field_name", "value", "exception"),
    (
        ("realized_import_cost", -0.01, ValueError),
        ("realized_export_revenue", float("nan"), ValueError),
        ("battery_degradation_cost", float("inf"), ValueError),
        ("realized_import_cost", True, TypeError),
        ("realized_export_revenue", True, TypeError),
        ("battery_degradation_cost", cast(Any, "1"), TypeError),
    ),
)
def test_input_rejects_invalid_non_negative_components(
    field_name: str,
    value: object,
    exception: type[Exception],
) -> None:
    values: dict[str, object] = {
        "realized_import_cost": 10.0,
        "realized_export_revenue": 1.0,
        "battery_degradation_cost": 0.5,
    }
    values[field_name] = value

    with pytest.raises(exception):
        ExtendedEconomicOutcomeInput(
            cast(Any, values["realized_import_cost"]),
            cast(Any, values["realized_export_revenue"]),
            cast(Any, values["battery_degradation_cost"]),
            _terminal_evidence(),
        )


def test_result_rejects_reconstructed_terminal_evidence_and_recomputed_terms() -> None:
    terminal_evidence = _terminal_evidence()
    outcome_input = ExtendedEconomicOutcomeInput(10.0, 1.0, 0.5, terminal_evidence)
    reconstructed = _terminal_evidence()

    with pytest.raises(ValueError, match="exact source identity"):
        ExtendedEconomicOutcomeEvidence(
            outcome_input,
            10.0,
            1.0,
            0.5,
            reconstructed,
            reconstructed.terminal_energy_value,
            10.0 - 1.0 + 0.5 - reconstructed.terminal_energy_value,
        )
    with pytest.raises(ValueError, match="exact input semantics"):
        ExtendedEconomicOutcomeEvidence(
            outcome_input,
            10.0,
            2.0,
            0.5,
            terminal_evidence,
            terminal_evidence.terminal_energy_value,
            10.0 - 2.0 + 0.5 - terminal_evidence.terminal_energy_value,
        )


def test_zero_extra_terms_match_task_163_without_calling_task_163() -> None:
    terminal_evidence = _terminal_evidence()
    extended = _calculate(10.0, 0.0, 0.0, terminal_evidence)
    task_163 = DeterministicEconomicOutcomeCalculator().calculate(
        EconomicOutcomeInput(10.0, terminal_evidence)
    )

    assert extended.adjusted_net_economic_cost == task_163.net_economic_cost


def test_boundary_is_abstract_stateless_and_explicit() -> None:
    signature = inspect.signature(ExtendedEconomicOutcomeBoundary.calculate)

    assert inspect.isabstract(ExtendedEconomicOutcomeBoundary)
    assert ExtendedEconomicOutcomeBoundary.__slots__ == ()
    assert DeterministicExtendedEconomicOutcomeCalculator.__slots__ == ()
    assert list(signature.parameters) == ["self", "outcome_input"]
    with pytest.raises(TypeError):
        cast(Any, ExtendedEconomicOutcomeBoundary)()
    assert not hasattr(DeterministicExtendedEconomicOutcomeCalculator(), "__dict__")


def test_public_api_and_dependency_isolation() -> None:
    assert {
        "ExtendedEconomicOutcomeInput",
        "ExtendedEconomicOutcomeEvidence",
        "ExtendedEconomicOutcomeBoundary",
        "DeterministicExtendedEconomicOutcomeCalculator",
    } <= set(optimization.__all__)

    source = Path("optimization/extended_economic_outcome.py").read_text(
        encoding="utf-8"
    )
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
        "optimization.economic_outcome",
        "optimization.economic_planning",
        "optimization.economic_grid_charge_value",
        "optimization.economic_multi_opportunity_candidate_planning",
    )
    assert not any(
        name == prefix or name.startswith(f"{prefix}.")
        for name in imports
        for prefix in forbidden
    )
