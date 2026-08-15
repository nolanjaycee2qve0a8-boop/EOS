"""Focused accounting-contract tests for TASK-169 export revenue evidence."""

import ast
import inspect
from dataclasses import FrozenInstanceError, fields
from pathlib import Path
from typing import Any, cast

import pytest

import optimization
from optimization import (
    BatteryOptimizationModel,
    DeterministicExportRevenueCalculator,
    DeterministicExtendedEconomicOutcomeCalculator,
    DeterministicTerminalEnergyValueCalculator,
    ExportRevenueBoundary,
    ExportRevenueEvidence,
    ExportRevenueInput,
    ExtendedEconomicOutcomeInput,
    TerminalEnergyValueInput,
)


def _calculate(
    realized_export_energy_kwh: float = 10.0,
    export_tariff_per_kwh: float = 0.30,
) -> ExportRevenueEvidence:
    return DeterministicExportRevenueCalculator().calculate(
        ExportRevenueInput(realized_export_energy_kwh, export_tariff_per_kwh)
    )


def test_contracts_are_frozen_slotted_and_preserve_exact_source_input_identity() -> (
    None
):
    revenue_input = ExportRevenueInput(10.0, 0.30)
    evidence = DeterministicExportRevenueCalculator().calculate(revenue_input)

    assert [field.name for field in fields(ExportRevenueInput)] == [
        "realized_export_energy_kwh",
        "export_tariff_per_kwh",
    ]
    assert [field.name for field in fields(ExportRevenueEvidence)] == [
        "source_input",
        "realized_export_energy_kwh",
        "export_tariff_per_kwh",
        "realized_export_revenue",
    ]
    assert evidence.source_input is revenue_input
    assert not hasattr(revenue_input, "__dict__")
    assert not hasattr(evidence, "__dict__")
    with pytest.raises(FrozenInstanceError):
        cast(Any, revenue_input).export_tariff_per_kwh = 0.25


def test_basic_multiplication_fixture() -> None:
    evidence = _calculate(10.0, 0.30)

    assert evidence.realized_export_revenue == pytest.approx(3.0)


def test_zero_export_energy_and_zero_tariff_produce_zero_revenue() -> None:
    zero_energy = _calculate(0.0, 0.30)
    zero_tariff = _calculate(5.0, 0.0)

    assert zero_energy.realized_export_revenue == 0.0
    assert zero_tariff.realized_export_revenue == 0.0


def test_higher_energy_and_tariff_increase_revenue_linearly() -> None:
    baseline = _calculate(5.0, 0.30)
    higher_energy = _calculate(10.0, 0.30)
    higher_tariff = _calculate(5.0, 0.60)

    assert (
        higher_energy.realized_export_revenue == baseline.realized_export_revenue * 2.0
    )
    assert (
        higher_tariff.realized_export_revenue == baseline.realized_export_revenue * 2.0
    )


@pytest.mark.parametrize(
    ("energy", "tariff", "exception"),
    (
        (-0.01, 0.30, ValueError),
        (10.0, -0.01, ValueError),
        (float("nan"), 0.30, ValueError),
        (10.0, float("inf"), ValueError),
        (True, 0.30, TypeError),
        (10.0, True, TypeError),
        (cast(Any, "10"), 0.30, TypeError),
    ),
)
def test_input_rejects_invalid_energy_and_tariff(
    energy: object,
    tariff: object,
    exception: type[Exception],
) -> None:
    with pytest.raises(exception):
        ExportRevenueInput(cast(Any, energy), cast(Any, tariff))


def test_result_rejects_reconstructed_values() -> None:
    revenue_input = ExportRevenueInput(10.0, 0.30)

    with pytest.raises(ValueError, match="exact input semantics"):
        ExportRevenueEvidence(revenue_input, 9.0, 0.30, 2.7)
    with pytest.raises(ValueError, match="must equal"):
        ExportRevenueEvidence(revenue_input, 10.0, 0.30, 2.0)


def test_semantic_compatibility_with_task_168_export_revenue_input() -> None:
    export_evidence = _calculate(10.0, 0.30)
    model = BatteryOptimizationModel(10.0, 0.20, 1.0, 3.0, 3.0, 0.95, 0.95)
    terminal_evidence = DeterministicTerminalEnergyValueCalculator().calculate(
        TerminalEnergyValueInput(0.20, model, 0.90)
    )
    extended_input = ExtendedEconomicOutcomeInput(
        10.0,
        export_evidence.realized_export_revenue,
        0.0,
        terminal_evidence,
    )
    extended_evidence = DeterministicExtendedEconomicOutcomeCalculator().calculate(
        extended_input
    )

    assert (
        extended_input.realized_export_revenue
        == export_evidence.realized_export_revenue
    )
    assert extended_evidence.realized_export_revenue == pytest.approx(3.0)


def test_boundary_is_abstract_stateless_and_explicit() -> None:
    signature = inspect.signature(ExportRevenueBoundary.calculate)

    assert inspect.isabstract(ExportRevenueBoundary)
    assert ExportRevenueBoundary.__slots__ == ()
    assert DeterministicExportRevenueCalculator.__slots__ == ()
    assert list(signature.parameters) == ["self", "revenue_input"]
    with pytest.raises(TypeError):
        cast(Any, ExportRevenueBoundary)()
    assert not hasattr(DeterministicExportRevenueCalculator(), "__dict__")


def test_public_api_and_dependency_isolation() -> None:
    assert {
        "ExportRevenueInput",
        "ExportRevenueEvidence",
        "ExportRevenueBoundary",
        "DeterministicExportRevenueCalculator",
    } <= set(optimization.__all__)

    source = Path("optimization/export_revenue.py").read_text(encoding="utf-8")
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
    )
    assert not any(
        name == prefix or name.startswith(f"{prefix}.")
        for name in imports
        for prefix in forbidden
    )
