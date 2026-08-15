"""Focused accounting-contract tests for TASK-170 degradation-cost evidence."""

import ast
import inspect
from dataclasses import FrozenInstanceError, fields
from pathlib import Path
from typing import Any, cast

import pytest

import optimization
from optimization import (
    BatteryDegradationCostBoundary,
    BatteryDegradationCostEvidence,
    BatteryDegradationCostInput,
    BatteryOptimizationModel,
    DeterministicBatteryDegradationCostCalculator,
    DeterministicExtendedEconomicOutcomeCalculator,
    DeterministicTerminalEnergyValueCalculator,
    ExtendedEconomicOutcomeInput,
    TerminalEnergyValueInput,
)


def _calculate(
    battery_throughput_kwh: float = 10.0,
    degradation_cost_per_throughput_kwh: float = 0.08,
) -> BatteryDegradationCostEvidence:
    return DeterministicBatteryDegradationCostCalculator().calculate(
        BatteryDegradationCostInput(
            battery_throughput_kwh,
            degradation_cost_per_throughput_kwh,
        )
    )


def test_contracts_are_frozen_slotted_and_preserve_exact_source_input_identity() -> (
    None
):
    degradation_input = BatteryDegradationCostInput(10.0, 0.08)
    evidence = DeterministicBatteryDegradationCostCalculator().calculate(
        degradation_input
    )

    assert [field.name for field in fields(BatteryDegradationCostInput)] == [
        "battery_throughput_kwh",
        "degradation_cost_per_throughput_kwh",
    ]
    assert [field.name for field in fields(BatteryDegradationCostEvidence)] == [
        "source_input",
        "battery_throughput_kwh",
        "degradation_cost_per_throughput_kwh",
        "battery_degradation_cost",
    ]
    assert evidence.source_input is degradation_input
    assert not hasattr(degradation_input, "__dict__")
    assert not hasattr(evidence, "__dict__")
    with pytest.raises(FrozenInstanceError):
        cast(Any, degradation_input).battery_throughput_kwh = 5.0


def test_basic_multiplication_fixture() -> None:
    evidence = _calculate(10.0, 0.08)

    assert evidence.battery_degradation_cost == pytest.approx(0.8)


def test_zero_throughput_and_zero_rate_produce_zero_cost() -> None:
    zero_throughput = _calculate(0.0, 0.08)
    zero_rate = _calculate(12.0, 0.0)

    assert zero_throughput.battery_degradation_cost == 0.0
    assert zero_rate.battery_degradation_cost == 0.0


def test_higher_throughput_and_rate_increase_cost_linearly() -> None:
    baseline = _calculate(5.0, 0.08)
    higher_throughput = _calculate(10.0, 0.08)
    higher_rate = _calculate(5.0, 0.16)

    assert (
        higher_throughput.battery_degradation_cost
        == baseline.battery_degradation_cost * 2.0
    )
    assert (
        higher_rate.battery_degradation_cost == baseline.battery_degradation_cost * 2.0
    )


@pytest.mark.parametrize(
    ("throughput", "rate", "exception"),
    (
        (-0.01, 0.08, ValueError),
        (10.0, -0.01, ValueError),
        (float("nan"), 0.08, ValueError),
        (10.0, float("inf"), ValueError),
        (True, 0.08, TypeError),
        (10.0, True, TypeError),
        (cast(Any, "10"), 0.08, TypeError),
    ),
)
def test_input_rejects_invalid_throughput_and_rate(
    throughput: object,
    rate: object,
    exception: type[Exception],
) -> None:
    with pytest.raises(exception):
        BatteryDegradationCostInput(cast(Any, throughput), cast(Any, rate))


def test_result_rejects_reconstructed_values() -> None:
    degradation_input = BatteryDegradationCostInput(10.0, 0.08)

    with pytest.raises(ValueError, match="exact input semantics"):
        BatteryDegradationCostEvidence(degradation_input, 9.0, 0.08, 0.72)
    with pytest.raises(ValueError, match="must equal"):
        BatteryDegradationCostEvidence(degradation_input, 10.0, 0.08, 0.7)


def test_semantic_compatibility_with_task_168_degradation_cost_input() -> None:
    degradation_evidence = _calculate(10.0, 0.08)
    model = BatteryOptimizationModel(10.0, 0.20, 1.0, 3.0, 3.0, 0.95, 0.95)
    terminal_evidence = DeterministicTerminalEnergyValueCalculator().calculate(
        TerminalEnergyValueInput(0.20, model, 0.90)
    )
    extended_input = ExtendedEconomicOutcomeInput(
        10.0,
        0.0,
        degradation_evidence.battery_degradation_cost,
        terminal_evidence,
    )
    extended_evidence = DeterministicExtendedEconomicOutcomeCalculator().calculate(
        extended_input
    )

    assert (
        extended_input.battery_degradation_cost
        == degradation_evidence.battery_degradation_cost
    )
    assert extended_evidence.battery_degradation_cost == pytest.approx(0.8)


def test_boundary_is_abstract_stateless_and_explicit() -> None:
    signature = inspect.signature(BatteryDegradationCostBoundary.calculate)

    assert inspect.isabstract(BatteryDegradationCostBoundary)
    assert BatteryDegradationCostBoundary.__slots__ == ()
    assert DeterministicBatteryDegradationCostCalculator.__slots__ == ()
    assert list(signature.parameters) == ["self", "degradation_input"]
    with pytest.raises(TypeError):
        cast(Any, BatteryDegradationCostBoundary)()
    assert not hasattr(DeterministicBatteryDegradationCostCalculator(), "__dict__")


def test_public_api_and_dependency_isolation() -> None:
    assert {
        "BatteryDegradationCostInput",
        "BatteryDegradationCostEvidence",
        "BatteryDegradationCostBoundary",
        "DeterministicBatteryDegradationCostCalculator",
    } <= set(optimization.__all__)

    source = Path("optimization/battery_degradation_cost.py").read_text(
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
        "optimization.control_plan",
        "optimization.battery_soc_projection",
        "optimization.battery_planning",
        "optimization.extended_economic_outcome",
    )
    assert not any(
        name == prefix or name.startswith(f"{prefix}.")
        for name in imports
        for prefix in forbidden
    )
