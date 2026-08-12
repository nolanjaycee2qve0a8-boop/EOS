"""Tests for battery power-horizon constraint evidence in optimization."""

import ast
import inspect
from abc import ABC
from dataclasses import FrozenInstanceError, fields
from datetime import UTC, datetime
from math import inf, nan
from pathlib import Path
from typing import Any, cast, get_type_hints

import pytest

import optimization
from decision_formation import DecisionIntent
from optimization import (
    BatteryPowerConstraintViolation,
    BatteryPowerHorizonConstraintBoundary,
    BatteryPowerHorizonConstraintEvaluation,
    BatteryPowerHorizonConstraintInput,
    DeterministicBatteryPowerHorizonConstraintEvaluator,
    OptimizationResult,
    OptimizationSolution,
    OptimizationSolutionStep,
)
from tests.unit.optimization.test_battery_planning_contracts import (
    make_model,
    make_problem,
)


class MinimalPowerConstraintBoundary(BatteryPowerHorizonConstraintBoundary):
    """Test-only boundary implementation with no evaluation behavior."""

    __slots__ = ()

    def evaluate(
        self,
        constraint_input: BatteryPowerHorizonConstraintInput,
    ) -> BatteryPowerHorizonConstraintEvaluation:
        return BatteryPowerHorizonConstraintEvaluation(constraint_input, True, ())


def make_constraint_input(
    steps: tuple[OptimizationSolutionStep, ...] = (),
) -> BatteryPowerHorizonConstraintInput:
    result = OptimizationResult(make_problem(), "optimal")
    solution = OptimizationSolution(result, steps)
    return BatteryPowerHorizonConstraintInput(solution, make_model())


def make_step(
    action: str,
    requested_power_kw: float,
    *,
    hour: int,
) -> OptimizationSolutionStep:
    return OptimizationSolutionStep(
        datetime(2026, 1, 1, hour, tzinfo=UTC),
        DecisionIntent(cast(Any, action)),
        requested_power_kw,
    )


def test_constraint_input_is_frozen_slotted_and_preserves_exact_identities() -> None:
    constraint_input = make_constraint_input()

    assert [field.name for field in fields(BatteryPowerHorizonConstraintInput)] == [
        "solution",
        "battery_model",
    ]
    assert constraint_input.solution is constraint_input.solution
    assert constraint_input.battery_model is constraint_input.battery_model
    assert not hasattr(constraint_input, "__dict__")
    with pytest.raises(FrozenInstanceError):
        cast(Any, constraint_input).solution = constraint_input.solution


def test_violation_is_frozen_slotted_and_preserves_exact_step_identity() -> None:
    source_step = make_step("charge", 6.5, hour=1)
    violation = BatteryPowerConstraintViolation(
        source_step,
        0,
        "charge_power_above_max",
        6.5,
        3.0,
    )

    assert [field.name for field in fields(BatteryPowerConstraintViolation)] == [
        "source_step",
        "step_index",
        "kind",
        "requested_power_kw",
        "limit_power_kw",
    ]
    assert violation.source_step is source_step
    assert not hasattr(violation, "__dict__")
    with pytest.raises(FrozenInstanceError):
        cast(Any, violation).step_index = 1


@pytest.mark.parametrize(
    ("index", "kind", "requested", "limit"),
    [
        (-1, "charge_power_above_max", 6.5, 3.0),
        (True, "charge_power_above_max", 6.5, 3.0),
        (0, "unsupported", 6.5, 3.0),
        (0, "charge_power_above_max", nan, 3.0),
        (0, "discharge_power_above_max", 5.0, inf),
    ],
)
def test_violation_rejects_invalid_machine_semantics_or_values(
    index: object,
    kind: object,
    requested: object,
    limit: object,
) -> None:
    source_step = make_step("charge", 6.5, hour=1)

    with pytest.raises((TypeError, ValueError)):
        BatteryPowerConstraintViolation(
            source_step,
            cast(Any, index),
            cast(Any, kind),
            cast(Any, requested),
            cast(Any, limit),
        )


def test_evaluation_is_frozen_slotted_and_rejects_contradictory_state() -> None:
    source_step = make_step("charge", 6.5, hour=1)
    constraint_input = make_constraint_input((source_step,))
    violation = BatteryPowerConstraintViolation(
        source_step,
        0,
        "charge_power_above_max",
        6.5,
        3.0,
    )
    evaluation = BatteryPowerHorizonConstraintEvaluation(constraint_input, True, ())

    assert [
        field.name for field in fields(BatteryPowerHorizonConstraintEvaluation)
    ] == [
        "source_input",
        "feasible",
        "violations",
    ]
    assert evaluation.source_input is constraint_input
    assert not hasattr(evaluation, "__dict__")
    with pytest.raises(FrozenInstanceError):
        cast(Any, evaluation).feasible = False
    with pytest.raises(ValueError, match="if and only if"):
        BatteryPowerHorizonConstraintEvaluation(constraint_input, True, (violation,))
    with pytest.raises(ValueError, match="if and only if"):
        BatteryPowerHorizonConstraintEvaluation(constraint_input, False, ())


def test_evaluation_rejects_reconstructed_or_misordered_step_evidence() -> None:
    first = make_step("charge", 6.5, hour=1)
    second = make_step("discharge", 5.0, hour=2)
    constraint_input = make_constraint_input((first, second))
    reconstructed_first = OptimizationSolutionStep(
        first.timestamp,
        first.intent,
        first.requested_power_kw,
    )
    first_violation = BatteryPowerConstraintViolation(
        first, 0, "charge_power_above_max", 6.5, 3.0
    )
    second_violation = BatteryPowerConstraintViolation(
        second, 1, "discharge_power_above_max", 5.0, 4.0
    )

    with pytest.raises(ValueError, match="exact solution step identity"):
        BatteryPowerHorizonConstraintEvaluation(
            constraint_input,
            False,
            (
                BatteryPowerConstraintViolation(
                    reconstructed_first,
                    0,
                    "charge_power_above_max",
                    6.5,
                    3.0,
                ),
            ),
        )
    with pytest.raises(ValueError, match="strict solution step order"):
        BatteryPowerHorizonConstraintEvaluation(
            constraint_input,
            False,
            (second_violation, first_violation),
        )


def test_power_constraint_boundary_contract() -> None:
    signature = inspect.signature(BatteryPowerHorizonConstraintBoundary.evaluate)
    hints = get_type_hints(BatteryPowerHorizonConstraintBoundary.evaluate)

    assert issubclass(BatteryPowerHorizonConstraintBoundary, ABC)
    assert inspect.isabstract(BatteryPowerHorizonConstraintBoundary)
    assert BatteryPowerHorizonConstraintBoundary.__slots__ == ()
    assert list(signature.parameters) == ["self", "constraint_input"]
    assert hints == {
        "constraint_input": BatteryPowerHorizonConstraintInput,
        "return": BatteryPowerHorizonConstraintEvaluation,
    }
    with pytest.raises(TypeError):
        BatteryPowerHorizonConstraintBoundary()  # type: ignore[abstract]


def test_minimal_boundary_is_stateless() -> None:
    boundary = MinimalPowerConstraintBoundary()
    evaluation = boundary.evaluate(make_constraint_input())

    assert evaluation.feasible is True
    assert evaluation.violations == ()
    assert MinimalPowerConstraintBoundary.__slots__ == ()
    assert not hasattr(boundary, "__dict__")


def test_empty_solution_and_valid_power_requests_are_feasible() -> None:
    evaluator = DeterministicBatteryPowerHorizonConstraintEvaluator()
    empty = evaluator.evaluate(make_constraint_input())
    valid = evaluator.evaluate(
        make_constraint_input(
            (
                make_step("charge", 2.0, hour=1),
                make_step("charge", 3.0, hour=2),
                make_step("discharge", 3.0, hour=3),
                make_step("discharge", 4.0, hour=4),
                make_step("idle", 0.0, hour=5),
            )
        )
    )

    assert empty.feasible is True
    assert empty.violations == ()
    assert valid.feasible is True
    assert valid.violations == ()


def test_evaluator_reports_charge_power_above_max_without_clipping() -> None:
    source_step = make_step("charge", 6.5, hour=1)
    constraint_input = make_constraint_input((source_step,))
    evaluation = DeterministicBatteryPowerHorizonConstraintEvaluator().evaluate(
        constraint_input
    )
    violation = evaluation.violations[0]

    assert evaluation.feasible is False
    assert violation.source_step is source_step
    assert violation.step_index == 0
    assert violation.kind == "charge_power_above_max"
    assert violation.requested_power_kw == 6.5
    assert violation.limit_power_kw == 3.0
    assert source_step.requested_power_kw == 6.5


def test_evaluator_reports_discharge_power_above_max_without_clipping() -> None:
    source_step = make_step("discharge", 5.0, hour=1)
    constraint_input = make_constraint_input((source_step,))
    evaluation = DeterministicBatteryPowerHorizonConstraintEvaluator().evaluate(
        constraint_input
    )
    violation = evaluation.violations[0]

    assert evaluation.feasible is False
    assert violation.kind == "discharge_power_above_max"
    assert violation.requested_power_kw == 5.0
    assert violation.limit_power_kw == 4.0
    assert source_step.requested_power_kw == 5.0


def test_evaluator_collects_all_power_violations_in_exact_solution_order() -> None:
    steps = (
        make_step("charge", 2.0, hour=1),
        make_step("charge", 6.0, hour=2),
        make_step("idle", 0.0, hour=3),
        make_step("discharge", 5.0, hour=4),
        make_step("charge", 7.0, hour=5),
    )
    original_powers = tuple(step.requested_power_kw for step in steps)
    evaluation = DeterministicBatteryPowerHorizonConstraintEvaluator().evaluate(
        make_constraint_input(steps)
    )

    assert evaluation.feasible is False
    assert [violation.step_index for violation in evaluation.violations] == [1, 3, 4]
    assert [violation.kind for violation in evaluation.violations] == [
        "charge_power_above_max",
        "discharge_power_above_max",
        "charge_power_above_max",
    ]
    assert evaluation.violations[0].source_step is steps[1]
    assert evaluation.violations[1].source_step is steps[3]
    assert evaluation.violations[2].source_step is steps[4]
    assert tuple(step.requested_power_kw for step in steps) == original_powers


def test_power_constraint_module_has_no_soc_or_execution_dependencies() -> None:
    module_path = Path(optimization.__file__).parent / "battery_power_constraint.py"
    tree = ast.parse(module_path.read_text(encoding="utf-8"))
    imported_modules = {
        node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
    }

    assert imported_modules == {
        "abc",
        "dataclasses",
        "math",
        "optimization.battery_planning",
        "optimization.solution",
        "typing",
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
        "optimization.battery_soc_constraint",
    ):
        assert forbidden_root not in imported_modules


def test_public_api_exports_power_constraint_contracts() -> None:
    assert (
        optimization.BatteryPowerConstraintViolation is BatteryPowerConstraintViolation
    )
    assert (
        optimization.BatteryPowerHorizonConstraintBoundary
        is BatteryPowerHorizonConstraintBoundary
    )
    assert (
        optimization.BatteryPowerHorizonConstraintEvaluation
        is BatteryPowerHorizonConstraintEvaluation
    )
    assert (
        optimization.BatteryPowerHorizonConstraintInput
        is BatteryPowerHorizonConstraintInput
    )
    assert (
        optimization.DeterministicBatteryPowerHorizonConstraintEvaluator
        is DeterministicBatteryPowerHorizonConstraintEvaluator
    )
