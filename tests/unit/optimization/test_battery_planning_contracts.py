"""Tests for immutable battery planning facts in the optimization layer."""

import ast
from dataclasses import FrozenInstanceError, fields
from datetime import UTC, datetime
from math import inf, nan
from pathlib import Path
from typing import Any, cast

import pytest

import optimization
from capability import (
    ActiveCapabilityCollection,
    AvailableCapabilityCollection,
    CapabilityDescriptor,
    CapabilityMatch,
    CapabilityMatchCollection,
    RequiredCapabilityCollection,
)
from ems_strategy import EMSContext
from forecast import ForecastHorizon, ForecastPoint
from kernel.decision import DecisionContext
from objective import ObjectiveCapabilityActivationComposition, ObjectiveDescriptor
from optimization import (
    BatteryOptimizationInput,
    BatteryOptimizationModel,
    BatteryOptimizationState,
    OptimizationObjective,
    OptimizationObjectiveCollection,
    OptimizationProblem,
)


def make_problem() -> OptimizationProblem:
    source_context = DecisionContext(
        timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        soc=0.5,
        battery_power_limit_kw=3.0,
        battery_energy_capacity_kwh=10.0,
        pv_power_kw=1.0,
        load_power_kw=1.0,
        grid_power_kw=0.0,
        electricity_price_cny_per_kwh=0.5,
        reserve_soc=0.2,
        export_limit_kw=5.0,
    )
    required = CapabilityDescriptor("optimization", "Required capability.")
    available = CapabilityDescriptor("optimization", "Available capability.")
    matches = CapabilityMatchCollection(
        RequiredCapabilityCollection((required,)),
        AvailableCapabilityCollection((available,)),
        (CapabilityMatch(required, available),),
        (),
    )
    context = EMSContext(
        source_context,
        ObjectiveCapabilityActivationComposition(
            ObjectiveDescriptor("cost", "Describe cost without solving it."),
            ActiveCapabilityCollection(matches, (available,), ()),
        ),
        available,
    )
    horizon = ForecastHorizon(
        (
            ForecastPoint(
                datetime(2026, 1, 1, 1, tzinfo=UTC),
                pv_power_kw=1.0,
                load_power_kw=2.0,
            ),
        )
    )
    return OptimizationProblem(
        context,
        horizon,
        OptimizationObjectiveCollection((OptimizationObjective("cost", "minimize"),)),
    )


def make_model() -> BatteryOptimizationModel:
    return BatteryOptimizationModel(
        usable_capacity_kwh=10.0,
        min_soc_fraction=0.1,
        max_soc_fraction=0.9,
        max_charge_power_kw=3.0,
        max_discharge_power_kw=4.0,
        charge_efficiency=0.95,
        discharge_efficiency=0.9,
    )


def test_state_is_frozen_slotted_and_accepts_soc_bounds() -> None:
    lower = BatteryOptimizationState(0.0)
    upper = BatteryOptimizationState(1.0)

    assert [field.name for field in fields(BatteryOptimizationState)] == [
        "soc_fraction"
    ]
    assert lower.soc_fraction == 0.0
    assert upper.soc_fraction == 1.0
    assert not hasattr(lower, "__dict__")
    with pytest.raises(FrozenInstanceError):
        cast(Any, lower).soc_fraction = 0.5


@pytest.mark.parametrize("value", [-0.1, 1.1, nan, inf, -inf, True])
def test_state_rejects_out_of_range_nonfinite_or_boolean_soc(value: object) -> None:
    with pytest.raises((TypeError, ValueError), match="soc_fraction"):
        BatteryOptimizationState(cast(Any, value))


def test_model_is_frozen_slotted_and_accepts_valid_planning_facts() -> None:
    model = make_model()

    assert [field.name for field in fields(BatteryOptimizationModel)] == [
        "usable_capacity_kwh",
        "min_soc_fraction",
        "max_soc_fraction",
        "max_charge_power_kw",
        "max_discharge_power_kw",
        "charge_efficiency",
        "discharge_efficiency",
    ]
    assert not hasattr(model, "__dict__")
    with pytest.raises(FrozenInstanceError):
        cast(Any, model).usable_capacity_kwh = 20.0


@pytest.mark.parametrize(
    "overrides",
    [
        {"usable_capacity_kwh": 0.0},
        {"usable_capacity_kwh": nan},
        {"usable_capacity_kwh": True},
        {"min_soc_fraction": -0.1},
        {"max_soc_fraction": 1.1},
        {"min_soc_fraction": 0.9, "max_soc_fraction": 0.9},
        {"min_soc_fraction": inf},
        {"max_charge_power_kw": 0.0},
        {"max_discharge_power_kw": -1.0},
        {"max_charge_power_kw": True},
        {"charge_efficiency": 0.0},
        {"charge_efficiency": 1.1},
        {"discharge_efficiency": nan},
        {"discharge_efficiency": True},
    ],
)
def test_model_rejects_invalid_numeric_or_physical_configuration(
    overrides: dict[str, object],
) -> None:
    values: dict[str, object] = {
        "usable_capacity_kwh": 10.0,
        "min_soc_fraction": 0.1,
        "max_soc_fraction": 0.9,
        "max_charge_power_kw": 3.0,
        "max_discharge_power_kw": 4.0,
        "charge_efficiency": 0.95,
        "discharge_efficiency": 0.9,
    }
    values.update(overrides)

    with pytest.raises((TypeError, ValueError)):
        BatteryOptimizationModel(**cast(Any, values))


def test_input_is_frozen_slotted_and_preserves_exact_caller_identities() -> None:
    problem = make_problem()
    state = BatteryOptimizationState(0.5)
    model = make_model()
    planning_input = BatteryOptimizationInput(problem, state, model)

    assert [field.name for field in fields(BatteryOptimizationInput)] == [
        "problem",
        "battery_state",
        "battery_model",
    ]
    assert planning_input.problem is problem
    assert planning_input.battery_state is state
    assert planning_input.battery_model is model
    assert not hasattr(planning_input, "__dict__")
    with pytest.raises(FrozenInstanceError):
        cast(Any, planning_input).battery_state = state


@pytest.mark.parametrize("position", [0, 1, 2])
def test_input_rejects_invalid_contract_types(position: int) -> None:
    valid = (make_problem(), BatteryOptimizationState(0.5), make_model())
    values = list(valid)
    values[position] = object()

    with pytest.raises(TypeError):
        BatteryOptimizationInput(*cast(Any, values))


def test_battery_planning_module_has_no_execution_or_constraint_dependency() -> None:
    module_path = Path(optimization.__file__).parent / "battery_planning.py"
    source = module_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_modules = {
        node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
    }

    assert imported_modules == {"dataclasses", "math", "optimization.model"}
    for forbidden_root in (
        "ems_strategy",
        "ems_simulator",
        "simulator",
        "runtime",
        "device",
        "dispatch",
        "execution",
        "scipy",
        "cvxpy",
        "pulp",
        "pyomo",
        "ortools",
    ):
        assert forbidden_root not in imported_modules


def test_public_api_exports_battery_planning_contracts() -> None:
    assert optimization.BatteryOptimizationState is BatteryOptimizationState
    assert optimization.BatteryOptimizationModel is BatteryOptimizationModel
    assert optimization.BatteryOptimizationInput is BatteryOptimizationInput
    for name in (
        "BatteryOptimizationInput",
        "BatteryOptimizationModel",
        "BatteryOptimizationState",
    ):
        assert name in optimization.__all__
