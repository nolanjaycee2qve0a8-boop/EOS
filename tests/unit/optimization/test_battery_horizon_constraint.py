"""Tests for aggregation of existing typed battery-horizon evidence."""

import ast
import inspect
from abc import ABC
from dataclasses import FrozenInstanceError, fields
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast, get_type_hints

import pytest

import optimization
from decision_formation import DecisionIntent
from optimization import (
    BatteryHorizonConstraintAggregateBoundary,
    BatteryHorizonConstraintEvaluation,
    BatteryHorizonConstraintInput,
    BatteryOptimizationModel,
    BatteryPowerConstraintViolation,
    BatteryPowerHorizonConstraintEvaluation,
    BatteryPowerHorizonConstraintInput,
    BatterySOCConstraintViolation,
    BatterySOCHorizonConstraintEvaluation,
    BatterySOCHorizonConstraintInput,
    BatterySOCHorizonProjection,
    BatterySOCProjectionStep,
    DeterministicBatteryHorizonConstraintAggregator,
    OptimizationSolution,
    OptimizationSolutionStep,
)
from tests.unit.optimization.test_battery_soc_projection import (
    make_model,
    make_projection_input,
)


class MinimalAggregateBoundary(BatteryHorizonConstraintAggregateBoundary):
    """Test-only aggregate boundary with no evaluator ownership."""

    __slots__ = ()

    def aggregate(
        self,
        aggregate_input: BatteryHorizonConstraintInput,
    ) -> BatteryHorizonConstraintEvaluation:
        return BatteryHorizonConstraintEvaluation(
            aggregate_input,
            aggregate_input.soc_evaluation.feasible
            and aggregate_input.power_evaluation.feasible,
        )


def make_evaluations(
    *,
    soc_feasible: bool,
    power_feasible: bool,
    soc_model: BatteryOptimizationModel | None = None,
    power_model: BatteryOptimizationModel | None = None,
    power_solution: OptimizationSolution | None = None,
) -> tuple[
    BatterySOCHorizonConstraintEvaluation,
    BatteryPowerHorizonConstraintEvaluation,
]:
    model = soc_model or make_model()
    source_step = OptimizationSolutionStep(
        datetime(2026, 1, 1, tzinfo=UTC),
        DecisionIntent("charge"),
        6.0,
    )
    projection_input = make_projection_input(model=model, steps=(source_step,))
    projection_step = BatterySOCProjectionStep(source_step, 0.5, 0.95, 4.5)
    projection = BatterySOCHorizonProjection(projection_input, (projection_step,))
    soc_input = BatterySOCHorizonConstraintInput(projection, model)
    if soc_feasible:
        soc_violations: tuple[BatterySOCConstraintViolation, ...] = ()
    else:
        soc_violations = (
            BatterySOCConstraintViolation(
                projection_step,
                0,
                "above_max_soc",
                0.95,
                model.max_soc_fraction,
            ),
        )
    soc_evaluation = BatterySOCHorizonConstraintEvaluation(
        soc_input,
        soc_feasible,
        soc_violations,
    )

    solution = power_solution or projection_input.solution
    power_model_value = power_model or model
    power_input = BatteryPowerHorizonConstraintInput(solution, power_model_value)
    if power_feasible:
        power_violations: tuple[BatteryPowerConstraintViolation, ...] = ()
    else:
        power_violations = (
            BatteryPowerConstraintViolation(
                solution.steps[0],
                0,
                "charge_power_above_max",
                solution.steps[0].requested_power_kw,
                power_model_value.max_charge_power_kw,
            ),
        )
    power_evaluation = BatteryPowerHorizonConstraintEvaluation(
        power_input,
        power_feasible,
        power_violations,
    )
    return soc_evaluation, power_evaluation


def test_input_is_frozen_slotted_and_preserves_exact_component_identities() -> None:
    soc_evaluation, power_evaluation = make_evaluations(
        soc_feasible=True,
        power_feasible=True,
    )
    aggregate_input = BatteryHorizonConstraintInput(soc_evaluation, power_evaluation)

    assert [field.name for field in fields(BatteryHorizonConstraintInput)] == [
        "soc_evaluation",
        "power_evaluation",
    ]
    assert aggregate_input.soc_evaluation is soc_evaluation
    assert aggregate_input.power_evaluation is power_evaluation
    assert not hasattr(aggregate_input, "__dict__")
    with pytest.raises(FrozenInstanceError):
        cast(Any, aggregate_input).soc_evaluation = soc_evaluation


def test_input_rejects_mismatched_exact_solution_identity() -> None:
    soc_evaluation, _ = make_evaluations(soc_feasible=True, power_feasible=True)
    source_solution = soc_evaluation.source_input.projection.source_input.solution
    reconstructed_solution = OptimizationSolution(
        source_solution.source_result,
        source_solution.steps,
    )
    _, power_evaluation = make_evaluations(
        soc_feasible=True,
        power_feasible=True,
        power_solution=reconstructed_solution,
    )

    with pytest.raises(ValueError, match="exact solution identity"):
        BatteryHorizonConstraintInput(soc_evaluation, power_evaluation)


def test_input_rejects_mismatched_exact_battery_model_identity() -> None:
    soc_evaluation, _ = make_evaluations(soc_feasible=True, power_feasible=True)
    source_model = soc_evaluation.source_input.battery_model
    reconstructed_model = type(source_model)(
        source_model.usable_capacity_kwh,
        source_model.min_soc_fraction,
        source_model.max_soc_fraction,
        source_model.max_charge_power_kw,
        source_model.max_discharge_power_kw,
        source_model.charge_efficiency,
        source_model.discharge_efficiency,
    )
    _, power_evaluation = make_evaluations(
        soc_feasible=True,
        power_feasible=True,
        soc_model=source_model,
        power_model=reconstructed_model,
        power_solution=soc_evaluation.source_input.projection.source_input.solution,
    )

    with pytest.raises(ValueError, match="exact battery model identity"):
        BatteryHorizonConstraintInput(soc_evaluation, power_evaluation)


@pytest.mark.parametrize(
    ("soc_feasible", "power_feasible", "expected"),
    [
        (True, True, True),
        (False, True, False),
        (True, False, False),
        (False, False, False),
    ],
)
def test_aggregate_feasibility_truth_table(
    soc_feasible: bool,
    power_feasible: bool,
    expected: bool,
) -> None:
    soc_evaluation, power_evaluation = make_evaluations(
        soc_feasible=soc_feasible,
        power_feasible=power_feasible,
    )
    aggregate_input = BatteryHorizonConstraintInput(soc_evaluation, power_evaluation)
    evaluation = DeterministicBatteryHorizonConstraintAggregator().aggregate(
        aggregate_input
    )

    assert evaluation.feasible is expected
    assert evaluation.source_input is aggregate_input


def test_result_is_frozen_slotted_and_rejects_contradictory_feasibility() -> None:
    soc_evaluation, power_evaluation = make_evaluations(
        soc_feasible=False,
        power_feasible=True,
    )
    aggregate_input = BatteryHorizonConstraintInput(soc_evaluation, power_evaluation)
    evaluation = BatteryHorizonConstraintEvaluation(aggregate_input, False)

    assert [field.name for field in fields(BatteryHorizonConstraintEvaluation)] == [
        "source_input",
        "feasible",
    ]
    assert evaluation.source_input is aggregate_input
    assert not hasattr(evaluation, "__dict__")
    with pytest.raises(FrozenInstanceError):
        cast(Any, evaluation).feasible = True
    with pytest.raises(ValueError, match="conjunction"):
        BatteryHorizonConstraintEvaluation(aggregate_input, True)


def test_aggregate_preserves_exact_typed_evidence_without_flattening_or_mutation() -> (
    None
):
    soc_evaluation, power_evaluation = make_evaluations(
        soc_feasible=False,
        power_feasible=False,
    )
    original_soc_violation = soc_evaluation.violations[0]
    original_power_violation = power_evaluation.violations[0]

    evaluation = DeterministicBatteryHorizonConstraintAggregator().aggregate(
        BatteryHorizonConstraintInput(soc_evaluation, power_evaluation)
    )

    assert evaluation.feasible is False
    assert evaluation.source_input.soc_evaluation is soc_evaluation
    assert evaluation.source_input.power_evaluation is power_evaluation
    assert (
        evaluation.source_input.soc_evaluation.violations[0] is original_soc_violation
    )
    assert (
        evaluation.source_input.power_evaluation.violations[0]
        is original_power_violation
    )
    assert not hasattr(evaluation, "violations")


def test_aggregate_boundary_contract() -> None:
    signature = inspect.signature(BatteryHorizonConstraintAggregateBoundary.aggregate)
    hints = get_type_hints(BatteryHorizonConstraintAggregateBoundary.aggregate)

    assert issubclass(BatteryHorizonConstraintAggregateBoundary, ABC)
    assert inspect.isabstract(BatteryHorizonConstraintAggregateBoundary)
    assert BatteryHorizonConstraintAggregateBoundary.__slots__ == ()
    assert list(signature.parameters) == ["self", "aggregate_input"]
    assert hints == {
        "aggregate_input": BatteryHorizonConstraintInput,
        "return": BatteryHorizonConstraintEvaluation,
    }
    with pytest.raises(TypeError):
        BatteryHorizonConstraintAggregateBoundary()  # type: ignore[abstract]


def test_minimal_aggregate_boundary_is_stateless() -> None:
    soc_evaluation, power_evaluation = make_evaluations(
        soc_feasible=True,
        power_feasible=True,
    )
    boundary = MinimalAggregateBoundary()
    result = boundary.aggregate(
        BatteryHorizonConstraintInput(soc_evaluation, power_evaluation)
    )

    assert result.feasible is True
    assert MinimalAggregateBoundary.__slots__ == ()
    assert not hasattr(boundary, "__dict__")


def test_aggregate_module_has_no_execution_or_strategy_dependency() -> None:
    module_path = Path(optimization.__file__).parent / "battery_horizon_constraint.py"
    tree = ast.parse(module_path.read_text(encoding="utf-8"))
    imported_modules = {
        node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
    }

    assert imported_modules == {
        "abc",
        "dataclasses",
        "optimization.battery_power_constraint",
        "optimization.battery_soc_constraint",
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
        "optimization.battery_soc_projection",
    ):
        assert forbidden_root not in imported_modules


def test_public_api_exports_aggregate_contracts() -> None:
    assert (
        optimization.BatteryHorizonConstraintAggregateBoundary
        is BatteryHorizonConstraintAggregateBoundary
    )
    assert (
        optimization.BatteryHorizonConstraintEvaluation
        is BatteryHorizonConstraintEvaluation
    )
    assert optimization.BatteryHorizonConstraintInput is BatteryHorizonConstraintInput
    assert (
        optimization.DeterministicBatteryHorizonConstraintAggregator
        is DeterministicBatteryHorizonConstraintAggregator
    )
