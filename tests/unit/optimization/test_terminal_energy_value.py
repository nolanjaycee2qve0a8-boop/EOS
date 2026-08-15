"""Focused contract tests for TASK-162 terminal stored-energy valuation."""

import ast
import inspect
from dataclasses import FrozenInstanceError, fields
from pathlib import Path
from typing import Any, cast

import pytest

import optimization
from optimization import (
    BatteryOptimizationModel,
    DeterministicTerminalEnergyValueCalculator,
    TerminalEnergyValueBoundary,
    TerminalEnergyValueEvidence,
    TerminalEnergyValueInput,
)


def _model() -> BatteryOptimizationModel:
    return BatteryOptimizationModel(10.0, 0.20, 1.0, 3.0, 3.0, 0.95, 0.95)


def _input(
    terminal_soc: float = 0.80,
    valuation_import_price: float = 0.90,
    *,
    model: BatteryOptimizationModel | None = None,
) -> TerminalEnergyValueInput:
    return TerminalEnergyValueInput(
        terminal_soc,
        _model() if model is None else model,
        valuation_import_price,
    )


def _calculate(value_input: TerminalEnergyValueInput) -> TerminalEnergyValueEvidence:
    return DeterministicTerminalEnergyValueCalculator().calculate(value_input)


def test_contracts_are_frozen_slotted_and_preserve_exact_model_identity() -> None:
    model = _model()
    value_input = _input(model=model)
    evidence = _calculate(value_input)

    assert [field.name for field in fields(TerminalEnergyValueInput)] == [
        "terminal_soc",
        "battery_model",
        "valuation_import_price",
    ]
    assert [field.name for field in fields(TerminalEnergyValueEvidence)] == [
        "source_input",
        "usable_soc_fraction",
        "usable_terminal_stored_energy_kwh",
        "discharge_efficiency",
        "deliverable_terminal_energy_kwh",
        "valuation_import_price",
        "value_per_stored_kwh",
        "terminal_energy_value",
    ]
    assert evidence.source_input is value_input
    assert evidence.source_input.battery_model is model
    assert not hasattr(value_input, "__dict__")
    assert not hasattr(evidence, "__dict__")
    with pytest.raises(FrozenInstanceError):
        cast(Any, value_input).terminal_soc = 0.20


def test_minimum_soc_and_zero_price_produce_zero_value() -> None:
    at_minimum = _calculate(_input(0.20, 0.90))
    zero_price = _calculate(_input(0.80, 0.0))

    assert at_minimum.usable_soc_fraction == 0.0
    assert at_minimum.usable_terminal_stored_energy_kwh == 0.0
    assert at_minimum.deliverable_terminal_energy_kwh == 0.0
    assert at_minimum.terminal_energy_value == 0.0
    assert zero_price.terminal_energy_value == 0.0
    assert zero_price.value_per_stored_kwh == 0.0


def test_example_fixture_applies_discharge_efficiency_and_price_in_order() -> None:
    evidence = _calculate(_input(0.80, 0.90))

    assert evidence.usable_soc_fraction == pytest.approx(0.60)
    assert evidence.usable_terminal_stored_energy_kwh == pytest.approx(6.0)
    assert evidence.discharge_efficiency == pytest.approx(0.95)
    assert evidence.deliverable_terminal_energy_kwh == pytest.approx(5.7)
    assert evidence.value_per_stored_kwh == pytest.approx(0.855)
    assert evidence.terminal_energy_value == pytest.approx(5.13)


def test_higher_terminal_soc_and_price_increase_terminal_value() -> None:
    low_soc = _calculate(_input(0.30, 0.90))
    high_soc = _calculate(_input(0.80, 0.90))
    low_price = _calculate(_input(0.80, 0.50))
    high_price = _calculate(_input(0.80, 0.90))

    assert high_soc.terminal_energy_value > low_soc.terminal_energy_value
    assert high_price.terminal_energy_value > low_price.terminal_energy_value


@pytest.mark.parametrize(
    ("terminal_soc", "valuation_import_price", "exception"),
    (
        (0.19, 0.90, ValueError),
        (1.01, 0.90, ValueError),
        (float("nan"), 0.90, ValueError),
        (float("inf"), 0.90, ValueError),
        (0.80, -0.01, ValueError),
        (0.80, float("nan"), ValueError),
        (0.80, float("inf"), ValueError),
        (True, 0.90, TypeError),
        (0.80, True, TypeError),
    ),
)
def test_input_rejects_invalid_soc_and_valuation_price(
    terminal_soc: float,
    valuation_import_price: float,
    exception: type[Exception],
) -> None:
    with pytest.raises(exception):
        _input(terminal_soc, valuation_import_price)


def test_boundary_is_abstract_and_calculator_has_no_instance_state() -> None:
    assert inspect.isabstract(TerminalEnergyValueBoundary)
    assert TerminalEnergyValueBoundary.__slots__ == ()
    assert DeterministicTerminalEnergyValueCalculator.__slots__ == ()
    with pytest.raises(TypeError):
        cast(Any, TerminalEnergyValueBoundary)()
    assert not hasattr(DeterministicTerminalEnergyValueCalculator(), "__dict__")


def test_public_api_and_dependency_isolation() -> None:
    public_names = set(optimization.__all__)
    assert {
        "TerminalEnergyValueInput",
        "TerminalEnergyValueEvidence",
        "TerminalEnergyValueBoundary",
        "DeterministicTerminalEnergyValueCalculator",
    } <= public_names

    source_path = Path("optimization/terminal_energy_value.py")
    source = source_path.read_text(encoding="utf-8")
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
        "kernel",
        "optimization.economic_planning",
        "optimization.economic_grid_charge_value",
    )
    assert not any(
        name == prefix or name.startswith(f"{prefix}.")
        for name in imports
        for prefix in forbidden
    )
