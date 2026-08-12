"""Tests for SOC-horizon constraint evidence in the optimization layer."""

import ast
import inspect
from abc import ABC
from dataclasses import FrozenInstanceError, fields
from datetime import UTC, datetime, timedelta
from math import inf, nan
from pathlib import Path
from typing import Any, cast, get_type_hints

import pytest

import optimization
from decision_formation import DecisionIntent
from optimization import (
    BatteryOptimizationModel,
    BatterySOCConstraintViolation,
    BatterySOCHorizonConstraintBoundary,
    BatterySOCHorizonConstraintEvaluation,
    BatterySOCHorizonConstraintInput,
    BatterySOCHorizonProjection,
    BatterySOCProjectionStep,
    DeterministicBatterySOCHorizonConstraintEvaluator,
    OptimizationSolutionStep,
)
from tests.unit.optimization.test_battery_soc_projection import (
    make_model,
    make_projection_input,
)


class MinimalConstraintBoundary(BatterySOCHorizonConstraintBoundary):
    """Test-only boundary implementation with no evaluation behavior."""

    __slots__ = ()

    def evaluate(
        self,
        constraint_input: BatterySOCHorizonConstraintInput,
    ) -> BatterySOCHorizonConstraintEvaluation:
        return BatterySOCHorizonConstraintEvaluation(constraint_input, True, ())


def make_constraint_input(
    ending_socs: tuple[float, ...],
    *,
    min_soc_fraction: float = 0.1,
    max_soc_fraction: float = 0.9,
) -> BatterySOCHorizonConstraintInput:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    solution_steps = tuple(
        OptimizationSolutionStep(
            start + timedelta(hours=index),
            DecisionIntent("idle"),
            0.0,
        )
        for index in range(len(ending_socs))
    )
    model = make_model(
        min_soc_fraction=min_soc_fraction,
        max_soc_fraction=max_soc_fraction,
    )
    projection_input = make_projection_input(model=model, steps=solution_steps)
    starting_soc = projection_input.battery_input.battery_state.soc_fraction
    projection_steps: list[BatterySOCProjectionStep] = []
    for source_step, ending_soc in zip(
        projection_input.solution.steps,
        ending_socs,
        strict=True,
    ):
        projection_steps.append(
            BatterySOCProjectionStep(
                source_step,
                starting_soc,
                ending_soc,
                ending_soc - starting_soc,
            )
        )
        starting_soc = ending_soc
    projection = BatterySOCHorizonProjection(projection_input, tuple(projection_steps))
    return BatterySOCHorizonConstraintInput(projection, model)


def test_constraint_input_is_frozen_slotted_and_preserves_exact_identities() -> None:
    constraint_input = make_constraint_input((0.68,))

    assert [field.name for field in fields(BatterySOCHorizonConstraintInput)] == [
        "projection",
        "battery_model",
    ]
    assert constraint_input.projection is constraint_input.projection
    assert (
        constraint_input.battery_model
        is constraint_input.projection.source_input.battery_input.battery_model
    )
    assert not hasattr(constraint_input, "__dict__")
    with pytest.raises(FrozenInstanceError):
        cast(Any, constraint_input).projection = constraint_input.projection


def test_constraint_input_rejects_reconstructed_value_equal_model() -> None:
    constraint_input = make_constraint_input((0.68,))
    model = constraint_input.battery_model
    reconstructed_model = BatteryOptimizationModel(
        model.usable_capacity_kwh,
        model.min_soc_fraction,
        model.max_soc_fraction,
        model.max_charge_power_kw,
        model.max_discharge_power_kw,
        model.charge_efficiency,
        model.discharge_efficiency,
    )

    with pytest.raises(ValueError, match="exact projection planning model identity"):
        BatterySOCHorizonConstraintInput(
            constraint_input.projection,
            reconstructed_model,
        )


@pytest.mark.parametrize(
    ("kind", "expected_limit"),
    [("below_min_soc", 0.1), ("above_max_soc", 0.9)],
)
def test_violation_is_frozen_slotted_and_preserves_exact_step_identity(
    kind: str,
    expected_limit: float,
) -> None:
    constraint_input = make_constraint_input((0.05,))
    source_step = constraint_input.projection.steps[0]
    violation = BatterySOCConstraintViolation(
        source_step,
        0,
        cast(Any, kind),
        source_step.ending_soc_fraction,
        expected_limit,
    )

    assert [field.name for field in fields(BatterySOCConstraintViolation)] == [
        "source_projection_step",
        "step_index",
        "kind",
        "soc_fraction",
        "limit_soc_fraction",
    ]
    assert violation.source_projection_step is source_step
    assert not hasattr(violation, "__dict__")
    with pytest.raises(FrozenInstanceError):
        cast(Any, violation).step_index = 1


@pytest.mark.parametrize(
    ("index", "kind", "soc", "limit"),
    [
        (-1, "below_min_soc", 0.05, 0.1),
        (True, "below_min_soc", 0.05, 0.1),
        (0, "unsupported", 0.05, 0.1),
        (0, "below_min_soc", nan, 0.1),
        (0, "above_max_soc", 0.95, inf),
    ],
)
def test_violation_rejects_invalid_machine_semantics_or_values(
    index: object,
    kind: object,
    soc: object,
    limit: object,
) -> None:
    source_step = make_constraint_input((0.05,)).projection.steps[0]

    with pytest.raises((TypeError, ValueError)):
        BatterySOCConstraintViolation(
            source_step,
            cast(Any, index),
            cast(Any, kind),
            cast(Any, soc),
            cast(Any, limit),
        )


def test_evaluation_is_frozen_slotted_and_rejects_contradictory_state() -> None:
    constraint_input = make_constraint_input((0.68,))
    evaluation = BatterySOCHorizonConstraintEvaluation(constraint_input, True, ())
    source_step = constraint_input.projection.steps[0]
    violation = BatterySOCConstraintViolation(
        source_step,
        0,
        "below_min_soc",
        0.05,
        0.1,
    )

    assert [field.name for field in fields(BatterySOCHorizonConstraintEvaluation)] == [
        "source_input",
        "feasible",
        "violations",
    ]
    assert evaluation.source_input is constraint_input
    assert not hasattr(evaluation, "__dict__")
    with pytest.raises(FrozenInstanceError):
        cast(Any, evaluation).feasible = False
    with pytest.raises(ValueError, match="if and only if"):
        BatterySOCHorizonConstraintEvaluation(constraint_input, True, (violation,))
    with pytest.raises(ValueError, match="if and only if"):
        BatterySOCHorizonConstraintEvaluation(constraint_input, False, ())


def test_evaluation_rejects_reconstructed_or_misordered_projection_step_evidence() -> (
    None
):
    constraint_input = make_constraint_input((0.05, 0.95))
    first, second = constraint_input.projection.steps
    reconstructed_first = BatterySOCProjectionStep(
        first.source_step,
        first.starting_soc_fraction,
        first.ending_soc_fraction,
        first.battery_energy_delta_kwh,
    )
    first_violation = BatterySOCConstraintViolation(
        first, 0, "below_min_soc", 0.05, 0.1
    )
    second_violation = BatterySOCConstraintViolation(
        second, 1, "above_max_soc", 0.95, 0.9
    )

    with pytest.raises(ValueError, match="exact projection step identity"):
        BatterySOCHorizonConstraintEvaluation(
            constraint_input,
            False,
            (
                BatterySOCConstraintViolation(
                    reconstructed_first,
                    0,
                    "below_min_soc",
                    0.05,
                    0.1,
                ),
            ),
        )
    with pytest.raises(ValueError, match="strict projection step order"):
        BatterySOCHorizonConstraintEvaluation(
            constraint_input,
            False,
            (second_violation, first_violation),
        )


def test_constraint_boundary_is_abstract_slotted_and_has_explicit_signature() -> None:
    signature = inspect.signature(BatterySOCHorizonConstraintBoundary.evaluate)
    hints = get_type_hints(BatterySOCHorizonConstraintBoundary.evaluate)

    assert issubclass(BatterySOCHorizonConstraintBoundary, ABC)
    assert inspect.isabstract(BatterySOCHorizonConstraintBoundary)
    assert BatterySOCHorizonConstraintBoundary.__slots__ == ()
    assert list(signature.parameters) == ["self", "constraint_input"]
    assert hints == {
        "constraint_input": BatterySOCHorizonConstraintInput,
        "return": BatterySOCHorizonConstraintEvaluation,
    }
    with pytest.raises(TypeError):
        BatterySOCHorizonConstraintBoundary()  # type: ignore[abstract]


def test_minimal_constraint_boundary_is_stateless() -> None:
    boundary = MinimalConstraintBoundary()
    evaluation = boundary.evaluate(make_constraint_input(()))

    assert evaluation.feasible is True
    assert evaluation.violations == ()
    assert MinimalConstraintBoundary.__slots__ == ()
    assert not hasattr(boundary, "__dict__")


def test_empty_and_valid_horizons_are_feasible() -> None:
    evaluator = DeterministicBatterySOCHorizonConstraintEvaluator()

    empty = evaluator.evaluate(make_constraint_input(()))
    valid = evaluator.evaluate(make_constraint_input((0.1, 0.68, 0.9)))

    assert empty.feasible is True
    assert empty.violations == ()
    assert valid.feasible is True
    assert valid.violations == ()


def test_evaluator_reports_above_max_with_original_unclamped_soc() -> None:
    constraint_input = make_constraint_input((0.95,))
    evaluation = DeterministicBatterySOCHorizonConstraintEvaluator().evaluate(
        constraint_input
    )
    violation = evaluation.violations[0]

    assert evaluation.feasible is False
    assert len(evaluation.violations) == 1
    assert violation.source_projection_step is constraint_input.projection.steps[0]
    assert violation.step_index == 0
    assert violation.kind == "above_max_soc"
    assert violation.soc_fraction == 0.95
    assert violation.limit_soc_fraction == 0.9


def test_evaluator_reports_below_min_with_original_unclamped_soc() -> None:
    constraint_input = make_constraint_input((-0.12,))
    evaluation = DeterministicBatterySOCHorizonConstraintEvaluator().evaluate(
        constraint_input
    )
    violation = evaluation.violations[0]

    assert evaluation.feasible is False
    assert violation.kind == "below_min_soc"
    assert violation.soc_fraction == -0.12
    assert violation.limit_soc_fraction == 0.1


def test_evaluator_does_not_evaluate_or_modify_requested_power() -> None:
    source_step = OptimizationSolutionStep(
        datetime(2026, 1, 1, tzinfo=UTC),
        DecisionIntent("charge"),
        50.0,
    )
    projection_input = make_projection_input(steps=(source_step,))
    projection_step = BatterySOCProjectionStep(source_step, 0.5, 0.68, 1.8)
    projection = BatterySOCHorizonProjection(projection_input, (projection_step,))
    constraint_input = BatterySOCHorizonConstraintInput(
        projection,
        projection_input.battery_input.battery_model,
    )

    evaluation = DeterministicBatterySOCHorizonConstraintEvaluator().evaluate(
        constraint_input
    )

    assert evaluation.feasible is True
    assert evaluation.violations == ()
    assert source_step.requested_power_kw == 50.0


def test_evaluator_collects_all_violations_in_projection_order() -> None:
    constraint_input = make_constraint_input((0.68, 1.16, 1.02, -0.12))
    original_steps = constraint_input.projection.steps
    original_powers = tuple(
        step.source_step.requested_power_kw for step in original_steps
    )
    evaluation = DeterministicBatterySOCHorizonConstraintEvaluator().evaluate(
        constraint_input
    )

    assert evaluation.feasible is False
    assert [violation.step_index for violation in evaluation.violations] == [1, 2, 3]
    assert [violation.kind for violation in evaluation.violations] == [
        "above_max_soc",
        "above_max_soc",
        "below_min_soc",
    ]
    assert evaluation.violations[0].source_projection_step is original_steps[1]
    assert evaluation.violations[1].source_projection_step is original_steps[2]
    assert evaluation.violations[2].source_projection_step is original_steps[3]
    assert (
        tuple(step.source_step.requested_power_kw for step in original_steps)
        == original_powers
    )


def test_constraint_module_has_no_forbidden_dependency() -> None:
    module_path = Path(optimization.__file__).parent / "battery_soc_constraint.py"
    tree = ast.parse(module_path.read_text(encoding="utf-8"))
    imported_modules = {
        node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
    }

    assert imported_modules == {
        "abc",
        "dataclasses",
        "math",
        "optimization.battery_planning",
        "optimization.battery_soc_projection",
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
    ):
        assert forbidden_root not in imported_modules


def test_public_api_exports_soc_constraint_contracts() -> None:
    assert optimization.BatterySOCConstraintViolation is BatterySOCConstraintViolation
    assert (
        optimization.BatterySOCHorizonConstraintBoundary
        is BatterySOCHorizonConstraintBoundary
    )
    assert (
        optimization.BatterySOCHorizonConstraintEvaluation
        is BatterySOCHorizonConstraintEvaluation
    )
    assert (
        optimization.BatterySOCHorizonConstraintInput
        is BatterySOCHorizonConstraintInput
    )
    assert (
        optimization.DeterministicBatterySOCHorizonConstraintEvaluator
        is DeterministicBatterySOCHorizonConstraintEvaluator
    )
