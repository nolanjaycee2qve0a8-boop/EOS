"""Tests for deterministic net-load-aware baseline candidate optimization."""

import ast
from dataclasses import FrozenInstanceError, fields
from math import inf, nan
from pathlib import Path
from typing import Any, cast

import pytest

import optimization
from forecast import ForecastPoint
from optimization import (
    BatteryOptimizationInput,
    BatteryOptimizationModel,
    BatteryOptimizationState,
    DeterministicBatteryHorizonConstraintAggregator,
    DeterministicBatteryPowerHorizonConstraintEvaluator,
    DeterministicBatterySOCHorizonConstraintEvaluator,
    DeterministicBatterySOCHorizonProjector,
    NetLoadAwareBaselineOptimizationConfiguration,
    NetLoadAwareBaselineOptimizer,
    OptimizationObjective,
    PhysicallyAwareBaselineOptimizationInput,
    PhysicallyAwareBaselineOptimizer,
)
from tests.unit.optimization.test_price_aware_baseline_optimizer import (
    make_problem,
    point,
)


def make_optimizer() -> NetLoadAwareBaselineOptimizer:
    return NetLoadAwareBaselineOptimizer(
        NetLoadAwareBaselineOptimizationConfiguration(0.3, 0.8, 3.0)
    )


def make_physical_input(
    points: tuple[ForecastPoint, ...],
    *,
    soc_fraction: float = 0.5,
    max_soc_fraction: float = 0.9,
    max_charge_power_kw: float = 3.0,
) -> PhysicallyAwareBaselineOptimizationInput:
    problem = make_problem(points)
    battery_model = BatteryOptimizationModel(
        10.0,
        0.1,
        max_soc_fraction,
        max_charge_power_kw,
        4.0,
        1.0,
        1.0,
    )
    return PhysicallyAwareBaselineOptimizationInput(
        BatteryOptimizationInput(
            problem,
            BatteryOptimizationState(soc_fraction),
            battery_model,
        ),
        3600.0,
    )


def test_configuration_is_frozen_slotted_and_validated() -> None:
    configuration = NetLoadAwareBaselineOptimizationConfiguration(0.3, 0.8, 3.0)

    assert [
        field.name for field in fields(NetLoadAwareBaselineOptimizationConfiguration)
    ] == [
        "low_price_threshold_cny_per_kwh",
        "high_price_threshold_cny_per_kwh",
        "requested_grid_charge_power_kw",
    ]
    assert not hasattr(configuration, "__dict__")
    with pytest.raises(FrozenInstanceError):
        cast(Any, configuration).requested_grid_charge_power_kw = 1.0
    for invalid in (True, nan, inf, 0.0, -1.0):
        with pytest.raises((TypeError, ValueError)):
            NetLoadAwareBaselineOptimizationConfiguration(0.3, 0.8, invalid)
    for low, high in ((True, 0.8), (0.3, False), (0.8, 0.3), (0.3, 0.3)):
        with pytest.raises((TypeError, ValueError)):
            NetLoadAwareBaselineOptimizationConfiguration(low, high, 3.0)


@pytest.mark.parametrize(
    ("price", "pv", "load", "action", "power"),
    [
        (0.3, 0.0, 0.7, "charge", 3.0),
        (0.55, 5.0, 0.9, "charge", 4.1),
        (0.9, 1.8, 1.2, "charge", 0.6),
        (None, 3.0, 1.0, "charge", 2.0),
        (0.9, 0.6, 1.8, "discharge", 1.2),
        (0.9, 0.1, 2.5, "discharge", 2.4),
        (0.9, 1.0, 1.0, "idle", 0.0),
        (0.55, 0.5, 1.5, "idle", 0.0),
        (None, 0.5, 1.5, "idle", 0.0),
    ],
)
def test_candidate_rules_follow_explicit_price_and_net_load_precedence(
    price: float | None,
    pv: float,
    load: float,
    action: str,
    power: float,
) -> None:
    problem = make_problem((point(1, price, pv=pv, load=load),))
    output = make_optimizer().solve_with_solution(problem)
    step = output.solution.steps[0]

    assert output.result.outcome == "optimal"
    assert step.intent.action == action
    assert step.requested_power_kw == pytest.approx(power)
    assert step.timestamp is problem.forecast_horizon.points[0].timestamp


def test_unsupported_objective_is_unavailable_with_empty_solution() -> None:
    problem = make_problem(
        (point(1, 0.9),),
        objectives=(OptimizationObjective("peak", "minimize"),),
    )
    output = make_optimizer().solve_with_solution(problem)

    assert output.result.outcome == "unavailable"
    assert output.solution.source_result is output.result
    assert output.solution.steps == ()


def test_multiple_forecasts_preserve_timestamp_order_and_determinism() -> None:
    problem = make_problem(
        (
            point(1, 0.9, pv=0.0, load=2.0),
            point(2, 0.5, pv=5.0, load=1.0),
            point(3, None, pv=0.5, load=1.5),
        )
    )

    first = make_optimizer().solve_with_solution(problem)
    second = make_optimizer().solve_with_solution(problem)

    assert [step.timestamp for step in first.solution.steps] == [
        forecast.timestamp for forecast in problem.forecast_horizon.points
    ]
    assert [
        (step.intent.action, step.requested_power_kw) for step in first.solution.steps
    ] == [
        (step.intent.action, step.requested_power_kw) for step in second.solution.steps
    ]


def test_composes_with_physical_revision_for_power_and_soc_evidence() -> None:
    candidate_optimizer = make_optimizer()
    physical_optimizer = PhysicallyAwareBaselineOptimizer(
        candidate_optimizer,
        DeterministicBatterySOCHorizonProjector(),
        DeterministicBatterySOCHorizonConstraintEvaluator(),
        DeterministicBatteryPowerHorizonConstraintEvaluator(),
        DeterministicBatteryHorizonConstraintAggregator(),
    )
    power_limited = make_physical_input(
        (point(1, 0.55, pv=6.0, load=0.0),),
        soc_fraction=0.1,
    )
    power_output = physical_optimizer.solve_physically(power_limited)

    assert power_output.candidate_output.solution.steps[0].requested_power_kw == 6.0
    assert power_output.final_output.solution.steps[0].requested_power_kw == 3.0
    assert power_output.revision.steps[0].reasons == ("charge_power_limit",)

    soc_limited = make_physical_input(
        (point(1, 0.55, pv=6.0, load=0.0),),
        soc_fraction=0.8,
        max_soc_fraction=0.9,
        max_charge_power_kw=10.0,
    )
    soc_output = physical_optimizer.solve_physically(soc_limited)

    assert soc_output.candidate_output.solution.steps[0].requested_power_kw == 6.0
    assert 0 < soc_output.final_output.solution.steps[0].requested_power_kw < 1.0
    assert soc_output.revision.steps[0].reasons == ("max_soc_limit",)


def test_module_has_no_battery_simulator_or_execution_dependencies() -> None:
    module_path = Path(optimization.__file__).parent / "net_load_aware_baseline.py"
    source = module_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_modules = {
        node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
    }

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
        "optimization.battery_planning",
        "optimization.physically_aware_baseline",
    ):
        assert forbidden_root not in imported_modules
    assert "BatteryOptimizationState" not in source
    assert "BatteryOptimizationModel" not in source


def test_public_api_exports_net_load_aware_optimizer() -> None:
    assert "NetLoadAwareBaselineOptimizationConfiguration" in optimization.__all__
    assert "NetLoadAwareBaselineOptimizer" in optimization.__all__
