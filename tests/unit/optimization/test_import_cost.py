"""Focused accounting-contract tests for TASK-171 import-cost evidence."""

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
    DeterministicImportCostCalculator,
    DeterministicTerminalEnergyValueCalculator,
    EconomicOutcomeInput,
    ExtendedEconomicOutcomeInput,
    ImportCostBoundary,
    ImportCostEvidence,
    ImportCostInput,
    TerminalEnergyValueEvidence,
    TerminalEnergyValueInput,
)


def _calculate(
    realized_import_energy_kwh: float = 10.0,
    import_tariff_per_kwh: float = 0.60,
) -> ImportCostEvidence:
    return DeterministicImportCostCalculator().calculate(
        ImportCostInput(realized_import_energy_kwh, import_tariff_per_kwh)
    )


def _terminal_evidence() -> TerminalEnergyValueEvidence:
    model = BatteryOptimizationModel(10.0, 0.20, 1.0, 3.0, 3.0, 0.95, 0.95)
    return DeterministicTerminalEnergyValueCalculator().calculate(
        TerminalEnergyValueInput(0.20, model, 0.90)
    )


def test_contracts_are_frozen_slotted_and_preserve_exact_source_input_identity() -> (
    None
):
    cost_input = ImportCostInput(10.0, 0.60)
    evidence = DeterministicImportCostCalculator().calculate(cost_input)

    assert [field.name for field in fields(ImportCostInput)] == [
        "realized_import_energy_kwh",
        "import_tariff_per_kwh",
    ]
    assert [field.name for field in fields(ImportCostEvidence)] == [
        "source_input",
        "realized_import_energy_kwh",
        "import_tariff_per_kwh",
        "realized_import_cost",
    ]
    assert evidence.source_input is cost_input
    assert not hasattr(cost_input, "__dict__")
    assert not hasattr(evidence, "__dict__")
    with pytest.raises(FrozenInstanceError):
        cast(Any, cost_input).import_tariff_per_kwh = 0.30


def test_basic_multiplication_fixture() -> None:
    assert _calculate(10.0, 0.60).realized_import_cost == pytest.approx(6.0)


def test_zero_import_energy_and_zero_tariff_produce_zero_cost() -> None:
    assert _calculate(0.0, 0.60).realized_import_cost == 0.0
    assert _calculate(5.0, 0.0).realized_import_cost == 0.0


def test_higher_energy_and_tariff_increase_cost_linearly() -> None:
    baseline = _calculate(5.0, 0.60)
    higher_energy = _calculate(10.0, 0.60)
    higher_tariff = _calculate(5.0, 1.20)

    assert higher_energy.realized_import_cost == baseline.realized_import_cost * 2.0
    assert higher_tariff.realized_import_cost == baseline.realized_import_cost * 2.0


@pytest.mark.parametrize(
    ("energy", "tariff", "exception"),
    (
        (-0.01, 0.60, ValueError),
        (10.0, -0.01, ValueError),
        (float("nan"), 0.60, ValueError),
        (10.0, float("inf"), ValueError),
        (True, 0.60, TypeError),
        (10.0, True, TypeError),
        (cast(Any, "10"), 0.60, TypeError),
    ),
)
def test_input_rejects_invalid_energy_and_tariff(
    energy: object,
    tariff: object,
    exception: type[Exception],
) -> None:
    with pytest.raises(exception):
        ImportCostInput(cast(Any, energy), cast(Any, tariff))


def test_result_rejects_reconstructed_values() -> None:
    cost_input = ImportCostInput(10.0, 0.60)

    with pytest.raises(ValueError, match="exact input semantics"):
        ImportCostEvidence(cost_input, 9.0, 0.60, 5.4)
    with pytest.raises(ValueError, match="must equal"):
        ImportCostEvidence(cost_input, 10.0, 0.60, 5.0)


def test_semantic_compatibility_with_task_168_and_task_163_inputs() -> None:
    import_evidence = _calculate(10.0, 0.60)
    terminal_evidence = _terminal_evidence()
    extended_input = ExtendedEconomicOutcomeInput(
        import_evidence.realized_import_cost,
        0.0,
        0.0,
        terminal_evidence,
    )
    outcome_input = EconomicOutcomeInput(
        import_evidence.realized_import_cost,
        terminal_evidence,
    )

    assert extended_input.realized_import_cost == pytest.approx(6.0)
    assert outcome_input.realized_import_cost == pytest.approx(6.0)
    assert (
        DeterministicExtendedEconomicOutcomeCalculator()
        .calculate(extended_input)
        .realized_import_cost
        == import_evidence.realized_import_cost
    )
    assert (
        DeterministicEconomicOutcomeCalculator()
        .calculate(outcome_input)
        .realized_import_cost
        == import_evidence.realized_import_cost
    )


def test_boundary_is_abstract_stateless_and_explicit() -> None:
    signature = inspect.signature(ImportCostBoundary.calculate)

    assert inspect.isabstract(ImportCostBoundary)
    assert ImportCostBoundary.__slots__ == ()
    assert DeterministicImportCostCalculator.__slots__ == ()
    assert list(signature.parameters) == ["self", "cost_input"]
    with pytest.raises(TypeError):
        cast(Any, ImportCostBoundary)()
    assert not hasattr(DeterministicImportCostCalculator(), "__dict__")


def test_public_api_and_dependency_isolation() -> None:
    assert {
        "ImportCostInput",
        "ImportCostEvidence",
        "ImportCostBoundary",
        "DeterministicImportCostCalculator",
    } <= set(optimization.__all__)

    source = Path("optimization/import_cost.py").read_text(encoding="utf-8")
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
        "optimization.control_plan",
        "optimization.extended_economic_outcome",
        "optimization.economic_outcome",
        "optimization.export_revenue",
    )
    assert not any(
        name == prefix or name.startswith(f"{prefix}.")
        for name in imports
        for prefix in forbidden
    )
